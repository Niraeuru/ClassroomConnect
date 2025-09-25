from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('admin', 'Admin'),
    ]
    
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='student')
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Fix related_name conflicts
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.',
        related_name='quiz_user_set',
        related_query_name='quiz_user',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        related_name='quiz_user_set',
        related_query_name='quiz_user',
    )
    
    def is_student(self):
        return self.role == 'student'
    
    def is_admin(self):
        return self.role == 'admin'

class Quiz(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, help_text="Optional description of the quiz")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Question(models.Model):
    QUESTION_TYPES = [
        ('mcq', 'Multiple Choice (Single Answer)'),
        ('checkbox', 'Multiple Choice (Multiple Answers)'),
        ('text', 'Text Input'),
        ('radio', 'Radio Button'),
    ]
    
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    text = models.CharField(max_length=500)
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES, default='mcq')
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.text


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    text = models.CharField(max_length=200)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.text
    