from rest_framework import serializers
from .models import Quiz, Question, Choice, Class

class ClassSerializer(serializers.ModelSerializer):
    class Meta:
        model = Class
        fields = ["id", "name", "description", "created_at"]

class ChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Choice
        fields = ["id", "text", "is_correct"]

class QuestionSerializer(serializers.ModelSerializer):
    choices = ChoiceSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = ["id", "text", "question_type", "choices", "order"]

class QuizSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)
    class_assigned = ClassSerializer(read_only=True)
    class_assigned_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Quiz
        fields = ["id", "title", "description", "class_assigned", "class_assigned_id", "created_at", "complete_by_date", "questions"]
