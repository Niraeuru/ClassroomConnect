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
        
        total_questions = questions.count()
        correct_answers = 0
        
        for question in questions:
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
            elif question.question_type == 'text':
                # Text input - for now, we'll count as correct if any answer is provided
                # In a real app, you might want to implement text matching logic
                if user_answer and user_answer.strip():
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
    
    return render(request, 'quiz/student_dashboard.html', {
        'quizzes': quizzes,
        'classes': classes,
        'search_query': search_query,
        'class_filter': class_filter,
        'completion_filter': completion_filter,
        'sort_by': sort_by,
        'completed_quiz_ids': completed_quiz_ids,
        'now': timezone.now()
    })