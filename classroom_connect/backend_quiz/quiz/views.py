from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Quiz, Question, Choice, User, Class, QuizAttempt
from .serializers import QuizSerializer
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Q, Prefetch
from django.utils import timezone
import json
import io
import re
from typing import List

# GET list of all quizzes
@api_view(["GET"])
def quiz_list(request):
    quizzes = Quiz.objects.all()
    serializer = QuizSerializer(quizzes, many=True)
    return Response(serializer.data)

# GET single quiz details
@api_view(["GET"])
def quiz_detail(request, pk):
    try:
        quiz = Quiz.objects.get(pk=pk)
    except Quiz.DoesNotExist:
        return Response({"error": "Quiz not found"}, status=404)
    
    serializer = QuizSerializer(quiz)
    return Response(serializer.data)

# POST quiz result (submit answers)
@api_view(["POST"])
def quiz_result(request):
    try:
        quiz_id = request.data.get('quiz_id')
        answers = request.data.get('answers', {})
        
        if not quiz_id:
            return Response({"error": "Quiz ID is required"}, status=400)
        
        quiz = Quiz.objects.get(pk=quiz_id)
        questions = quiz.questions.all()
        
        # Only auto-grade non-text questions
        autograded_questions = questions.exclude(question_type='text')
        total_questions = autograded_questions.count()
        correct_answers = 0
        
        for question in autograded_questions:
            question_key = f"question_{question.id}"
            user_answer = answers.get(question_key)
            
            if question.question_type == 'mcq_single':
                # Single choice question
                if user_answer:
                    try:
                        selected_choice = Choice.objects.get(id=user_answer, question=question)
                        if selected_choice.is_correct:
                            correct_answers += 1
                    except Choice.DoesNotExist:
                        pass
            elif question.question_type == 'mcq_multiple':
                # Multiple choice question
                if user_answer and isinstance(user_answer, list):
                    correct_choices = question.choices.filter(is_correct=True).count()
                    selected_correct = 0
                    selected_incorrect = 0
                    
                    for choice_id in user_answer:
                        try:
                            choice = Choice.objects.get(id=choice_id, question=question)
                            if choice.is_correct:
                                selected_correct += 1
                            else:
                                selected_incorrect += 1
                        except Choice.DoesNotExist:
                            pass
                    
                    # Only count as correct if all correct choices are selected and no incorrect ones
                    if selected_correct == correct_choices and selected_incorrect == 0:
                        correct_answers += 1
            elif question.question_type == 'true_false':
                # True/False question
                if user_answer is not None:
                    try:
                        # For true/false, we expect the answer to be a boolean or string representation
                        if isinstance(user_answer, str):
                            user_answer = user_answer.lower() in ['true', '1', 'yes']
                        elif isinstance(user_answer, int):
                            user_answer = bool(user_answer)
                        
                        # Get the correct answer from the first choice (True/False questions have only one choice)
                        correct_choice = question.choices.first()
                        if correct_choice and correct_choice.is_correct == user_answer:
                            correct_answers += 1
                    except (ValueError, AttributeError):
                        pass
        
        percentage = round((correct_answers / total_questions) * 100) if total_questions > 0 else 0
        
        # Create or update quiz attempt record
        attempt, created = QuizAttempt.objects.get_or_create(
            user=request.user,
            quiz=quiz,
            defaults={
                'score': correct_answers,
                'total_questions': total_questions,
                'percentage': percentage
            }
        )
        
        if not created:
            # Update existing attempt
            attempt.score = correct_answers
            attempt.total_questions = total_questions
            attempt.percentage = percentage
            attempt.completed_at = timezone.now()
            attempt.save()
        
        return Response({
            "quiz_id": quiz_id,
            "total_questions": total_questions,
            "correct_answers": correct_answers,
            "percentage": percentage,
            "score": f"{correct_answers}/{total_questions}"
        })
    except Quiz.DoesNotExist:
        return Response({"error": "Quiz not found"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)

def home_page(request):
    return render(request, "quiz/home.html")

def quiz_detail_page(request, quiz_id):
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    
    # Check if user has already completed this quiz
    if request.user.is_authenticated and request.user.is_student():
        attempt = QuizAttempt.objects.filter(user=request.user, quiz=quiz).first()
        if attempt:
            messages.info(request, 'You have already completed this quiz.')
            return redirect('student_dashboard')
    
    questions = quiz.questions.all()
    return render(request, "quiz/quiz_detail_page.html", {"quiz": quiz, "questions": questions})

def quiz_result_page(request, quiz_id):
    return render(request, "quiz/quiz_result.html", {"quiz_id": quiz_id})

@login_required
def create_quiz(request):
    if not request.user.is_admin():
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('student_dashboard')
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # Create quiz
            class_assigned = None
            if data.get('class_assigned_id'):
                try:
                    class_assigned = Class.objects.get(id=data['class_assigned_id'])
                except Class.DoesNotExist:
                    pass
            
            complete_by_date = None
            if data.get('complete_by_date'):
                try:
                    complete_by_date = timezone.datetime.fromisoformat(data['complete_by_date'].replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    pass
            
            quiz = Quiz.objects.create(
                title=data['title'],
                description=data.get('description', ''),
                class_assigned=class_assigned,
                complete_by_date=complete_by_date
            )
            
            # Create questions
            for question_data in data['questions']:
                question = Question.objects.create(
                    quiz=quiz,
                    text=question_data['text'],
                    question_type=question_data['type'],
                    order=question_data.get('order', 0)
                )
                
                # Create choices for MCQ and True/False questions
                if question_data['type'] in ['mcq_single', 'mcq_multiple', 'true_false']:
                    for choice_data in question_data['choices']:
                        Choice.objects.create(
                            question=question,
                            text=choice_data['text'],
                            is_correct=choice_data['is_correct'],
                            order=choice_data.get('order', 0)
                        )
            
            return JsonResponse({'success': True, 'quiz_id': quiz.id})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    # Ensure default classes exist
    default_class_names = [
        "Cloud Computing",
        "Professional ethics",
        "Software Testing",
        "Computer Networks",
        "Machine Learning",
        "Human Computer Interactions",
        "Social Networking and Web Mining",
        "Devops",
        "Entrepreneurship",
    ]
    for class_name in default_class_names:
        Class.objects.get_or_create(name=class_name)

    # Get classes for the form
    classes = Class.objects.all()
    return render(request, "quiz/create_quiz.html", {'classes': classes})

@login_required
def generate_questions_from_document(request):
    if not request.user.is_admin():
        return JsonResponse({'success': False, 'error': 'Access denied. Admin privileges required.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)

    upload = request.FILES.get('document')
    # New controls: allow separate counts for MCQ and Text
    try:
        mcq_count = int(request.POST.get('mcq_count', '0'))
    except ValueError:
        mcq_count = 0
    try:
        tf_count = int(request.POST.get('tf_count', '0'))
    except ValueError:
        tf_count = 0
    try:
        text_count = int(request.POST.get('text_count', '5'))
    except ValueError:
        text_count = 5
    
    # Hardcoded Gemini API key
    gemini_api_key = "AIzaSyCxBRJ5agNpCLfC1IUVQtdJ2GYSzZs75gA"  

    if not upload:
        return JsonResponse({'success': False, 'error': 'No document uploaded'}, status=400)

    filename = upload.name.lower()
    text_content = ''

    # Basic support: plain text files. Optional support for .pdf and .docx when packages are available.
    if filename.endswith('.txt') or filename.endswith('.md'):
        try:
            bytes_data = upload.read()
            text_content = bytes_data.decode('utf-8', errors='ignore')
        except Exception:
            return JsonResponse({'success': False, 'error': 'Failed to read the uploaded file as text.'}, status=400)
    elif filename.endswith('.pdf'):
        try:
            # Optional dependency: PyPDF2
            from PyPDF2 import PdfReader  # type: ignore
            reader = PdfReader(upload)
            pages_text: List[str] = []
            for page in reader.pages:
                try:
                    pages_text.append(page.extract_text() or '')
                except Exception:
                    pages_text.append('')
            text_content = '\n'.join(pages_text)
        except Exception:
            return JsonResponse({'success': False, 'error': 'PDF parsing failed. Please ensure PyPDF2 is installed or upload a .txt/.md file.'}, status=400)
    elif filename.endswith('.docx'):
        try:
            # Optional dependency: python-docx
            from docx import Document  # type: ignore
            # Read uploaded InMemoryUploadedFile into Document
            file_bytes = upload.read()
            file_stream = io.BytesIO(file_bytes)
            doc = Document(file_stream)
            paragraphs = [p.text for p in doc.paragraphs]
            text_content = '\n'.join(paragraphs)
        except Exception:
            return JsonResponse({'success': False, 'error': 'DOCX parsing failed. Please ensure python-docx is installed or upload a .txt/.md file.'}, status=400)
    else:
        return JsonResponse({'success': False, 'error': 'Unsupported file type. Please upload a .txt, .md, .pdf or .docx file.'}, status=400)

    # Simple sentence splitting
    sentences = re.split(r'(?:\.|\?|\!)\s+', text_content)
    cleaned = [s.strip() for s in sentences if len(s.strip()) > 20]
    if not cleaned:
        return JsonResponse({'success': False, 'error': 'The document does not contain enough readable text.'}, status=400)

    def build_text_questions(sentences: List[str], count: int) -> List[dict]:
        qs: List[dict] = []
        for idx, sentence in enumerate(sentences[:max(0, count)]):
            sentence = sentence.strip()
            if not sentence:
                continue
            # Create an open-ended question prompt based on the sentence content
            prompt = f"Explain in your own words: {sentence}"
            qs.append({
                'text': prompt,
                'type': 'text',
                'order': idx,
                'choices': []
            })
        return qs

    def build_mcq_questions(sentences: List[str], count: int) -> List[dict]:
        qs: List[dict] = []
        base_sentences = [s.strip() for s in sentences if s.strip()]
        if not base_sentences:
            return qs

        for idx in range(min(count, len(base_sentences))):
            correct_sentence = base_sentences[idx % len(base_sentences)]
            # Create a question about which statement matches the content
            question_text = "Which of the following statements is supported by the text?"

            # Select distractor sentences from other parts of the text
            distractors = []
            j = 1
            while len(distractors) < 3 and j < len(base_sentences):
                candidate = base_sentences[(idx + j) % len(base_sentences)]
                if candidate != correct_sentence and candidate not in distractors:
                    distractors.append(candidate)
                j += 1

            # Truncate long sentences to keep choices readable
            def truncate(s: str) -> str:
                s = s.strip()
                return (s[:140] + '…') if len(s) > 140 else s

            choices_texts = [truncate(correct_sentence)] + [truncate(d) for d in distractors]
            # Pad with generic distractors if needed
            generic_pool = [
                "A detail not discussed in the text.",
                "A statement that contradicts the text.",
                "An unrelated claim not supported by the text."
            ]
            k = 0
            while len(choices_texts) < 4 and k < len(generic_pool):
                choices_texts.append(generic_pool[k])
                k += 1

            choices = []
            for c_idx, choice_text in enumerate(choices_texts[:4]):
                choices.append({
                    'text': choice_text,
                    'is_correct': c_idx == 0,
                    'order': c_idx
                })

            qs.append({
                'text': question_text,
                'type': 'mcq_single',
                'order': idx,
                'choices': choices
            })
        return qs

    def build_tf_questions(sentences: List[str], count: int) -> List[dict]:
        qs: List[dict] = []
        base_sentences = [s.strip() for s in sentences if s.strip()]
        if not base_sentences:
            return qs
        for idx in range(min(count, len(base_sentences))):
            statement = base_sentences[idx % len(base_sentences)]
            # Alternate truth value for variety
            is_true = (idx % 2 == 0)
            choices = [
                {'text': 'True', 'is_correct': is_true, 'order': 0},
                {'text': 'False', 'is_correct': not is_true, 'order': 1},
            ]
            qs.append({
                'text': f"True or False: {statement}",
                'type': 'true_false',
                'order': idx,
                'choices': choices
            })
        return qs

    # Use Gemini API if key is set, otherwise fallback to basic generation
    if gemini_api_key and gemini_api_key != "Enter api key here":
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            # Create prompt for Gemini with exact counts
            prompt = f"""Read the text and ask {mcq_count} mcq questions, {tf_count} true/false questions, and {text_count} text based questions on it.

            Text content:
            {text_content[:4000]}  # Limit content to avoid token limits

            For multiple choice questions:
            - Create meaningful questions that test understanding of the content
            - Provide 4 choices each with one correct answer
            - Make incorrect choices plausible but clearly wrong
            - Ask about key concepts, facts, and relationships from the text

            For true/false questions:
            - Create factually checkable statements from the text
            - Mark the correct truth value in the JSON choices

            For text questions:
            - Create open-ended questions that require explanation or analysis
            - Ask for definitions, explanations, or critical thinking about the content
            - Make questions specific to the material

            IMPORTANT: Generate EXACTLY {mcq_count} MCQ, EXACTLY {tf_count} True/False, and EXACTLY {text_count} Text questions. Total: {mcq_count + tf_count + text_count} questions.

            Return the response as a JSON array with this exact format:
            [
                {{
                    "text": "Question text here",
                    "type": "mcq_single" or "true_false" or "text",
                    "choices": [
                        {{"text": "Choice 1", "is_correct": true}},
                        {{"text": "Choice 2", "is_correct": false}},
                        {{"text": "Choice 3", "is_correct": false}},
                        {{"text": "Choice 4", "is_correct": false}}
                    ]
                }}
            ]

            For text questions, include an empty choices array: "choices": []
            """
            
            response = model.generate_content(prompt)
            ai_questions = json.loads(response.text)
            
            # Validate and format the response, ensuring exact counts
            questions = []
            mcq_generated = 0
            tf_generated = 0
            text_generated = 0
            
            for q in ai_questions:
                if 'text' in q and 'type' in q:
                    # Check if we need more of this type
                    if q['type'] == 'mcq_single' and mcq_generated < mcq_count:
                        question = {
                            'text': q['text'],
                            'type': q['type'],
                            'order': len(questions),
                            'choices': q.get('choices', [])
                        }
                        questions.append(question)
                        mcq_generated += 1
                    elif q['type'] == 'true_false' and tf_generated < tf_count:
                        # Ensure TF choices are formatted properly
                        tf_choices = q.get('choices', [])
                        if not tf_choices or len(tf_choices) < 2:
                            tf_choices = [
                                {'text': 'True', 'is_correct': True, 'order': 0},
                                {'text': 'False', 'is_correct': False, 'order': 1},
                            ]
                        question = {
                            'text': q['text'],
                            'type': 'true_false',
                            'order': len(questions),
                            'choices': tf_choices[:2]
                        }
                        questions.append(question)
                        tf_generated += 1
                    elif q['type'] == 'text' and text_generated < text_count:
                        question = {
                            'text': q['text'],
                            'type': q['type'],
                            'order': len(questions),
                            'choices': []
                        }
                        questions.append(question)
                        text_generated += 1
                    
                    # Stop if we have enough of both types
                    if mcq_generated >= mcq_count and tf_generated >= tf_count and text_generated >= text_count:
                        break
            
            # If we don't have enough questions, fill with basic generation
            if len(questions) < (mcq_count + tf_count + text_count):
                remaining_mcq = max(0, mcq_count - mcq_generated)
                remaining_tf = max(0, tf_count - tf_generated)
                remaining_text = max(0, text_count - text_generated)
                
                if remaining_mcq > 0 or remaining_tf > 0 or remaining_text > 0:
                    basic_mcq = build_mcq_questions(cleaned, remaining_mcq)
                    basic_tf = build_tf_questions(cleaned, remaining_tf)
                    basic_text = build_text_questions(cleaned, remaining_text)
                    
                    # Add basic questions with proper ordering
                    for q in basic_mcq:
                        q['order'] = len(questions)
                        questions.append(q)
                    for q in basic_tf:
                        q['order'] = len(questions)
                        questions.append(q)
                    for q in basic_text:
                        q['order'] = len(questions)
                        questions.append(q)
            
            return JsonResponse({'success': True, 'questions': questions})
            
        except Exception as e:
            # Fallback to basic generation if Gemini fails
            pass
    
    # Basic generation (fallback or when no API key)
    text_qs = build_text_questions(cleaned, text_count)
    mcq_qs = build_mcq_questions(cleaned[text_count:], mcq_count) if mcq_count > 0 else []
    tf_qs = build_tf_questions(cleaned[text_count + mcq_count:], tf_count) if tf_count > 0 else []

    questions = []
    # Interleave MCQ first, then text (or vice versa). Keep simple: MCQ then text.
    questions.extend(mcq_qs)
    for q in tf_qs:
        q['order'] = len(questions)
        questions.append(q)
    # Adjust order continuation
    for i, q in enumerate(text_qs, start=len(questions)):
        q['order'] = i
        questions.append(q)

    return JsonResponse({'success': True, 'questions': questions})

@login_required
def edit_quiz(request, quiz_id):
    if not request.user.is_admin():
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('student_dashboard')
    
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # Update quiz
            quiz.title = data['title']
            quiz.description = data.get('description', '')
            
            # Update class assignment
            if data.get('class_assigned_id'):
                try:
                    quiz.class_assigned = Class.objects.get(id=data['class_assigned_id'])
                except Class.DoesNotExist:
                    quiz.class_assigned = None
            else:
                quiz.class_assigned = None
            
            # Update complete by date
            if data.get('complete_by_date'):
                try:
                    quiz.complete_by_date = timezone.datetime.fromisoformat(data['complete_by_date'].replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    quiz.complete_by_date = None
            else:
                quiz.complete_by_date = None
            
            quiz.save()
            
            # Delete existing questions and choices
            quiz.questions.all().delete()
            
            # Create new questions
            for question_data in data['questions']:
                question = Question.objects.create(
                    quiz=quiz,
                    text=question_data['text'],
                    question_type=question_data['type'],
                    order=question_data.get('order', 0)
                )
                
                # Create choices
                if question_data['type'] in ['mcq_single', 'mcq_multiple', 'true_false']:
                    for choice_data in question_data['choices']:
                        Choice.objects.create(
                            question=question,
                            text=choice_data['text'],
                            is_correct=choice_data['is_correct'],
                            order=choice_data.get('order', 0)
                        )
            
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return render(request, "quiz/edit_quiz.html", {'quiz': quiz})

@login_required
def delete_quiz(request, quiz_id):
    if not request.user.is_admin():
        return JsonResponse({'success': False, 'error': 'Access denied. Admin privileges required.'})
    
    if request.method == 'POST':
        quiz = get_object_or_404(Quiz, pk=quiz_id)
        quiz.delete()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

# Authentication Views
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'quiz/login.html')

def logout_view(request):
    logout(request)
    return redirect('login')

def register_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        role = request.POST.get('role', 'student')
        
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
            return render(request, 'quiz/register.html')
        
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            role=role
        )
        login(request, user)
        return redirect('dashboard')
    
    return render(request, 'quiz/register.html')

@login_required
def dashboard(request):
    if request.user.is_admin():
        return redirect('admin_dashboard')
    else:
        return redirect('student_dashboard')

@login_required
def admin_dashboard(request):
    if not request.user.is_admin():
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('student_dashboard')
    
    quizzes = Quiz.objects.select_related('class_assigned').all().order_by('class_assigned__name', '-created_at')
    classes = Class.objects.all()
    return render(request, 'quiz/admin_dashboard.html', {'quizzes': quizzes, 'classes': classes})

@login_required
def create_class(request):
    if not request.user.is_admin():
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('student_dashboard')
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            class_obj = Class.objects.create(
                name=data['name'],
                description=data.get('description', '')
            )
            return JsonResponse({'success': True, 'class_id': class_obj.id})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return render(request, "quiz/create_class.html")

@login_required
def student_dashboard(request):
    if not request.user.is_student():
        messages.error(request, 'Access denied. Student privileges required.')
        return redirect('admin_dashboard')
    
    # Get filter and sort parameters
    search_query = request.GET.get('search', '')
    class_filter = request.GET.get('class', '')
    completion_filter = request.GET.get('completion', '')
    sort_by = request.GET.get('sort', 'newest')
    
    # Base queryset with only current user's attempts prefetched
    quizzes = Quiz.objects.select_related('class_assigned').prefetch_related(
        Prefetch('attempts', queryset=QuizAttempt.objects.filter(user=request.user), to_attr='my_attempts')
    )
    
    # Apply search filter
    if search_query:
        quizzes = quizzes.filter(
            Q(title__icontains=search_query) | 
            Q(description__icontains=search_query)
        )
    
    # Apply class filter
    if class_filter:
        quizzes = quizzes.filter(class_assigned_id=class_filter)
    
    # Apply sorting
    if sort_by == 'oldest':
        quizzes = quizzes.order_by('created_at')
    else:  # newest (default)
        quizzes = quizzes.order_by('-created_at')
    
    # Get all classes for filter dropdown
    classes = Class.objects.all()
    
    # Get user's completed quiz IDs
    completed_quiz_ids = QuizAttempt.objects.filter(user=request.user).values_list('quiz_id', flat=True)
    
    # Apply completion filter
    if completion_filter == 'completed':
        quizzes = quizzes.filter(id__in=completed_quiz_ids)
    elif completion_filter == 'not_completed':
        quizzes = quizzes.exclude(id__in=completed_quiz_ids)
    
    # Quizzes that contain text questions (require manual grading)
    quizzes_requiring_manual = set(
        Quiz.objects.filter(questions__question_type='text').values_list('id', flat=True)
    )

    return render(request, 'quiz/student_dashboard.html', {
        'quizzes': quizzes,
        'classes': classes,
        'search_query': search_query,
        'class_filter': class_filter,
        'completion_filter': completion_filter,
        'sort_by': sort_by,
        'completed_quiz_ids': completed_quiz_ids,
        'now': timezone.now(),
        'quizzes_requiring_manual': quizzes_requiring_manual
    })