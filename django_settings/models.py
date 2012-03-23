# -*- coding: utf-8 -*-
from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.db.models.signals import post_save
from django.utils.translation import ugettext_lazy as _
from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError
import django.dispatch


import logging
log = logging.getLogger('django_settings.models')

class BaseSetting(models.Model):
    class Meta:
        abstract = True

    def __unicode__(self):
        return u'%s' % self.value


class String(BaseSetting):
    value = models.CharField(max_length=254)


class Integer(BaseSetting):
    value = models.IntegerField()


class PositiveInteger(BaseSetting):
    value = models.PositiveIntegerField()


class TimedeltaField(models.CharField):
    u'''
    Store Python's `dateutil.relativedelta` in a database string
    '''
    __metaclass__=models.SubfieldBase
    
    @staticmethod
    def _validate(value):
        if not isinstance(value, relativedelta):
            raise ValidationError('Not a relative time delta')
        
    
    def __init__(self, *args, **kwargs):
        kwargs['max_length'] = kwargs.get('max_length', 48)
        super(TimedeltaField, self).__init__(*args, **kwargs)
        self.validators = [ TimedeltaField._validate ]


    def to_python(self, value):
        if (value is None) or isinstance(value, relativedelta):
            return value
        try:
            return relativedelta(**eval('dict(%s)' % value))
        except:
            raise ValidationError('Not a real time delta. Please use value hours=xx,minutes=xx,...')

    def get_internal_type(self):
        return 'CharField'
    
    def get_prep_value(self, value):
        if isinstance(value,relativedelta):
            return ','.join('%s=%d' % (name, value) for (name,value) in filter(lambda x: x[0][0] != '_' and x[1], value.__dict__.iteritems()))
        return value

    def formfield(self, *args, **kwargs):
        defaults = {}
        defaults.update(kwargs)
        return super(TimedeltaField, self).formfield(*args, **defaults)

    def value_to_string(self, obj):
        value = self._get_val_from_obj(obj)
        return self.get_prep_value(value)


class TimeDelta(BaseSetting):
    '''
    timedelta type setting
    
    This setting is expressed the parameters you would give to `dateutil.relativedelta`, such as
    
    months=3,days=2
    
    It is useful to express expiration times 
    '''
    value = TimedeltaField()
    

# This signal allows caching of the settings in memory
setting_modified = django.dispatch.Signal(providing_args=["name", "value"]) 
    

class SettingManager(models.Manager):
    def get_value(self, name, **kw):
        if 'default' in kw:
            if not self.value_object_exists(name):
                return kw.get('default')
        setting_object = self.get(name=name).setting_object
        return setting_object.value

    def value_object_exists(self, name):
        queryset = self.filter(name=name)
        return queryset.exists() and queryset[0].setting_object

    def set_value(self, name, SettingClass, value):
        setting = Setting(name=name)

        if self.value_object_exists(name):
            setting = self.get(name=name)
            setting_object = setting.setting_object
            setting_object.delete()

        setting.setting_object = SettingClass.objects.create(value=value)
        setting.save()
        setting_modified.send(self, name=setting.name, value=setting.setting_object.value)
        return setting

class Setting(models.Model):
    class Meta:
        verbose_name = _('Setting')
        verbose_name_plural = _('Settings')

    objects = SettingManager()

    setting_type = models.ForeignKey(ContentType)
    setting_id = models.PositiveIntegerField()
    setting_object = generic.GenericForeignKey('setting_type', 'setting_id')

    name = models.CharField(max_length=255)
    
    def get_string_value(self):
        field = self.setting_object._meta._name_map['value'][0]
        return field.value_to_string(self.setting_object)
    string_value=property(get_string_value)
    
    def get_value(self):
        return self.setting_object.value
    
    def set_value(self, value):
        self.setting_object.value = value
        
    value=property(get_value, set_value)
            
        

def auto_refreshable_setting(name):
    
    # define the value
    _value = Setting.objects.get_value(name)
    
    # define a signal handler that will update the value if needed
    def signal_handler(sender, **kwargs):
        if kwargs['name'] == name:
            log.debug("setting with name %s updated to %s" % (kwargs['name'],kwargs['value']) )
            _value = kwargs['value']
            
    # connect the handler
    setting_modified.connect(signal_handler,weak=False)
    
    # define the getter that will return our cached property
    def getter():
        return _value
    
    # return the getter
    return getter
        