"""Closed, host-neutral input contracts. No provider or model credentials."""
import json
from datetime import date
from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_VERSION = 'coach-core/1.0'
RULE_VERSION = 'core02-marathon-1'


class CoreError(ValueError):
    pass


def obj(properties, required=()):
    return dict(type='object', properties=properties, required=list(required), additionalProperties=False)


TEXT = dict(type='string', maxLength=1000)
DAY = dict(type='string', format='date')
SYMPTOM = obj(dict(location=dict(type='string', minLength=1, maxLength=80),
                   kind=dict(enum=['pain', 'cramp_warning', 'soreness', 'limping', 'severe_symptom']),
                   severity=dict(type='integer', minimum=1, maximum=10),
                   persistent=dict(type='boolean'), recurring=dict(type='boolean')),
              ['location', 'kind'])
SYMPTOMS = dict(anyOf=[dict(type='null'), dict(type='array', items=SYMPTOM, maxItems=10)])
GOAL = obj(dict(event=dict(type='string', minLength=1, maxLength=200),
                date=dict(anyOf=[DAY, dict(type='null')]), date_window=dict(type=['string', 'null'], maxLength=100),
                date_range=obj(dict(start=DAY,end=DAY),['start','end']),
                role=dict(enum=['A', 'B', 'C', 'test']),
                distance_m=dict(type=['number', 'null'], exclusiveMinimum=0, maximum=200000),
                target_time_s=dict(type=['number', 'null'], exclusiveMinimum=0),
                source=TEXT), ['event', 'date', 'date_window', 'role', 'distance_m', 'target_time_s', 'source'])
REFERENCE = obj(dict(metric=dict(enum=['easy_pace_s_km', 'easy_hr_bpm']),
                     lower=dict(type='number', exclusiveMinimum=0), upper=dict(type='number', exclusiveMinimum=0),
                     basis=dict(enum=['user_confirmed', 'estimated']), source=TEXT),
                ['metric', 'lower', 'upper', 'basis', 'source'])
TRAINING_STATUS = obj(dict(mode=dict(enum=['normal_preparation','post_race_recovery','rebuilding']),
    assessment_date=DAY,recovery=dict(enum=['ready','impaired','unknown']),
    daily_function_normal=dict(type=['boolean','null']),easy_run_tolerated=dict(type=['boolean','null']),
    source=dict(type='string',minLength=1,maxLength=1000)),
    ['mode','assessment_date','recovery','daily_function_normal','easy_run_tolerated','source'])
PROFILE = obj(dict(goals=dict(type='array', items=GOAL, maxItems=10),
                   plan_program=dict(enum=['marathon']), training_status=TRAINING_STATUS,
                   rest_weekdays=dict(type='array',items=dict(type='integer',minimum=0,maximum=6),uniqueItems=True,maxItems=6),
                   training_weekdays=dict(anyOf=[dict(type='null'), dict(type='array', minItems=1, maxItems=6,
                       uniqueItems=True, items=dict(type='integer', minimum=0, maximum=6))]),
                   preferences=dict(type='array', items=TEXT, maxItems=15),
                   reference_ranges=dict(type='array', items=REFERENCE, maxItems=10),
                   current_symptoms=SYMPTOMS),
              ['goals', 'training_weekdays', 'preferences', 'reference_ranges', 'current_symptoms'])
FEEDBACK = obj(dict(rpe=dict(type=['integer', 'null'], minimum=1, maximum=10),
                    next_day_recovery=dict(enum=['good','poor','unknown']),
                    fatigue=dict(enum=[None, 'low', 'moderate', 'high']), symptoms=SYMPTOMS,
                    notes=TEXT, observed_at=dict(type='string', format='date-time')),
               ['rpe', 'fatigue', 'symptoms', 'notes', 'observed_at'])


def validate(value, schema):
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError):
        raise CoreError('INVALID_JSON_VALUE') from None
    if not Draft202012Validator(schema, format_checker=FormatChecker()).is_valid(value):
        raise CoreError('INPUT_SCHEMA_INVALID')
    if schema is PROFILE:
        if set(value.get('rest_weekdays',[])) & set(value.get('training_weekdays') or []):raise CoreError('REST_TRAINING_DAY_CONFLICT')
        for goal in value['goals']:
            if goal.get('date_range') and goal['date_range']['start']>goal['date_range']['end']:raise CoreError('GOAL_DATE_RANGE_INVALID')
            if goal.get('date_range') and (date.fromisoformat(goal['date_range']['end'])-date.fromisoformat(goal['date_range']['start'])).days>62:raise CoreError('GOAL_DATE_RANGE_TOO_BROAD')
        for reference in value['reference_ranges']:
            if reference['lower'] > reference['upper']:
                raise CoreError('REFERENCE_ORDER_INVALID')
    return value


def contracts():
    return dict(schema_version=SCHEMA_VERSION, inputs=dict(profile=PROFILE, feedback=FEEDBACK),
                operations={
                    'get_coach_context': dict(effects='read_local', parameters=obj({})),
                    'analyze_activity': dict(effects='read_local', parameters=obj(dict(activity_id=dict(oneOf=[dict(type='integer', minimum=1), dict(const='latest')])))),
                    'get_training_plan': dict(effects='read_local', parameters=obj(dict(version=dict(type='integer', minimum=1)))),
                    'create_plan_draft': dict(effects='write_draft_local', parameters=obj(dict(start=DAY,program=dict(enum=['auto','marathon'])), ['start'])),
                    'submit_activity_feedback': dict(effects='write_feedback_local', parameters=obj(dict(activity_id=dict(type='integer', minimum=1), feedback=FEEDBACK, supersedes=dict(type='string', maxLength=64)), ['activity_id','feedback'])),
                    'propose_plan_adjustment': dict(effects='write_proposal_local', parameters=obj(dict(feedback_id=TEXT, days=dict(type='integer', minimum=3, maximum=7)), ['feedback_id'])),
                }, trusted_local_only=['profile_update', 'confirm_plan', 'approve_proposal', 'reject_proposal', 'rollback_proposal'],
                boundary='No network API. Bind one instance outside model input. No arbitrary DB, SQL, URL, token, or confirmed flag.')
