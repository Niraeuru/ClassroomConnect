from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Quiz, Question, Choice
from .serializers import QuizSerializer
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse
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
            
            if question.question_type in ['mcq', 'radio']:
                # Single choice question
                if user_answer:
                    try:
                        selected_choice = Choice.objects.get(id=user_answer, question=question)
                        if selected_choice.is_correct:
                            correct_answers += 1
                    except Choice.DoesNotExist:
                        pass
            elif question.question_type == 'checkbox':
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
        
        percentage = round((correct_answers / total_questions) * 100) if total_questions > 0 else 0
        
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

def quiz_list_page(request):
    quizzes = Quiz.objects.all()
    return render(request, "quiz/quiz_list_page.html", {"quizzes": quizzes})

def quiz_detail_page(request, quiz_id):
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    questions = quiz.questions.all()
    return render(request, "quiz/quiz_detail_page.html", {"quiz": quiz, "questions": questions})

def quiz_result_page(request, quiz_id):
    return render(request, "quiz/quiz_result.html", {"quiz_id": quiz_id})

def create_quiz(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # Create quiz
            quiz = Quiz.objects.create(
                title=data['title'],
                description=data.get('description', '')
            )
            
            # Create questions
            for question_data in data['questions']:
                question = Question.objects.create(
                    quiz=quiz,
                    text=question_data['text'],
                    question_type=question_data['type'],
                    order=question_data.get('order', 0)
                )
                
                # Create choices for MCQ, checkbox, and radio questions
                if question_data['type'] in ['mcq', 'checkbox', 'radio']:
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
    
    return render(request, "quiz/create_quiz.html")

def edit_quiz(request, quiz_id):
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # Update quiz
            quiz.title = data['title']
            quiz.description = data.get('description', '')
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
                if question_data['type'] in ['mcq', 'checkbox', 'radio']:
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

def delete_quiz(request, quiz_id):
    if request.method == 'POST':
        quiz = get_object_or_404(Quiz, pk=quiz_id)
        quiz.delete()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Invalid request method'})