# -*- coding: utf-8 -*-
from django import forms
from django.db.models import Q
from django.forms.models import modelform_factory
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import ugettext_lazy as _
from django.utils.encoding import smart_unicode

from django_settings import models


class SettingForm(forms.ModelForm):
    class Meta:
        model = models.Setting
        fields = ('setting_type', 'name')

    value = forms.CharField()
    setting_modules = ['django_settings.models']
    
    @classmethod
    def get_setting_types_filter(cls):
        '''
        Creates a filter from all classes that derive from BaseSetting
        in the modules listed in `settings_modules`. This allows
        adding setting types that are part of another application
        '''
        if hasattr(cls, '_settings_types_filter'):
            return cls._settings_types_filter
        else:
            q = Q()
            import sys
            for module_name in cls.setting_modules:
                try:
                    __import__(module_name)
                except:
                    continue
                for name in filter(lambda x: x[0] != '_', dir(sys.modules[module_name])):
                    model_attribute = getattr(models, name)
                    if isinstance(model_attribute, type) and model_attribute.__bases__[0].__name__.endswith('BaseSetting'):
                        q |= Q(name=smart_unicode(model_attribute._meta.verbose_name_raw))
            return q
    

    def __init__(self, *a, **kw):
        forms.ModelForm.__init__(self, *a, **kw)

        self.fields['setting_type'].queryset = ContentType.objects.filter(self.__class__.get_setting_types_filter())

        instance = kw.get('instance')
        if instance:
            self.fields['value'].initial = instance.string_value

    def clean(self):
        cd = self.cleaned_data
        SettingClass = cd['setting_type'].model_class()
        SettingClassForm = modelform_factory(SettingClass)

        value = cd.get('value')
        if not value:
            self._errors['value'] = self.error_class(['Value field cannot be empty.'])
        else:
            setting_form = SettingClassForm({'value': cd['value']})
            if not setting_form.is_valid():
                del cd['value']
                self._errors['value'] = setting_form.errors['value']
            else:
                cd['value'] = setting_form.cleaned_data['value']
        return cd

    def save(self, *args, **kwargs):
        cd = self.clean()

        if self.instance and self.instance.setting_id:
            setting_object = self.instance.setting_object
            setting_object.delete()

        SettingClass = cd['setting_type'].model_class()
        setting_object = SettingClass.objects.create(value=cd['value'])

        kwargs['commit'] = False
        instance = forms.ModelForm.save(self, *args, **kwargs)
        instance.setting_id = setting_object.id
        instance.save()
        models.setting_modified.send(self, name=instance.name, value=setting_object.value)

        return instance
