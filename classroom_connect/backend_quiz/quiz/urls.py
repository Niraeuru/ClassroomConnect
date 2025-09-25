from django.urls import path
from . import views

urlpatterns = [
    # Authentication
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register_view, name="register"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("admin-dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("student-dashboard/", views.student_dashboard, name="student_dashboard"),
    
    # Frontend pages
    path("", views.home_page, name="home"),
    path("quizzes/", views.quiz_list_page, name="quiz_list_page"),
    path("quiz/<int:quiz_id>/", views.quiz_detail_page, name="quiz_detail_page"),
    path("quiz/<int:quiz_id>/result/", views.quiz_result_page, name="quiz_result_page"),
    
    # Quiz management (admin only)
    path("create-quiz/", views.create_quiz, name="create_quiz"),
    path("edit-quiz/<int:quiz_id>/", views.edit_quiz, name="edit_quiz"),
    path("delete-quiz/<int:quiz_id>/", views.delete_quiz, name="delete_quiz"),
    
    # API endpoints (moved to end to avoid conflicts)
    path("api/quizzes/", views.quiz_list, name="quiz_list"),
    path("api/quizzes/<int:pk>/", views.quiz_detail, name="quiz_detail"),
    path("api/results/", views.quiz_result, name="quiz_result"),
]
