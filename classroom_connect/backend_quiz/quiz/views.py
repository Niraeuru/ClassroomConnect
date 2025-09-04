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
    # For now just return what user submitted
    return Response({
        "message": "Quiz result received",
        "data": request.data
    })

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