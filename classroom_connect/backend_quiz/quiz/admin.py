from django.contrib import admin
from .models import Quiz, Question, Choice

class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 2  # show 2 empty choice fields by default


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1


class QuizAdmin(admin.ModelAdmin):
    inlines = [QuestionInline]


class QuestionAdmin(admin.ModelAdmin):
    inlines = [ChoiceInline]


admin.site.register(Quiz, QuizAdmin)
admin.site.register(Question, QuestionAdmin)
admin.site.register(Choice)
