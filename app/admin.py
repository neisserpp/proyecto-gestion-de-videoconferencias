from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Moderator, Reserve, Local

# Register your models here.

admin.site.register(CustomUser, UserAdmin)
admin.site.register(Moderator)
admin.site.register(Reserve)
admin.site.register(Local)


