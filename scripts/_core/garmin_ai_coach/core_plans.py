"""One conservative scheduling rule set shared by every future host adapter.

These are explicit engineering guardrails, not a validated physiological model.
No threshold, VDOT, injury diagnosis, or recovered-percent is inferred.
"""
from copy import deepcopy
from datetime import date, timedelta
from statistics import median

from .core_schema import RULE_VERSION, CoreError
from .core_analysis import history, safe_summary


def legacy_profile(value):
    goals = []
    for item in value.get('goals', []):
        goals.append(dict(event=item.get('event', '未命名目标'), date=item.get('date'),
                          date_window=item.get('date_window'), role=item.get('role', 'test'),
                          distance_m=item.get('distance_m'), target_time_s=item.get('target_time_s'),
                          source=item.get('source_type', value.get('source', 'legacy local profile'))))
    return dict(goals=goals, training_weekdays=None, preferences=[], reference_ranges=[], current_symptoms=None)


def training_basis(conn, as_of):
    windows = history(conn, as_of)
    recent_long = []
    for row in conn.execute("SELECT id,local_date FROM activity WHERE count_status='counted' AND kind IN ('running','track_running') AND local_date BETWEEN ? AND ? ORDER BY local_date DESC,id DESC",
                            ((as_of-timedelta(days=27)).isoformat(), as_of.isoformat())):
        facts, _ = safe_summary(conn, row['id'])
        if facts['distance_m'] is not None and facts['distance_m'] >= 30000:
            recent_long.append(dict(activity_id=row['id'], date=row['local_date'], distance_m=facts['distance_m']))
    from .queries import complete_weeks
    recent=[]
    for row in conn.execute("SELECT id FROM activity WHERE count_status='counted' AND kind IN ('running','track_running') AND local_date BETWEEN ? AND ? ORDER BY local_date,id",((as_of-timedelta(days=41)).isoformat(),as_of.isoformat())):
        facts,raw=safe_summary(conn,row[0])
        recent.append({k:facts[k] for k in ['id','local_date','distance_m','timer_s','lap_status']})
    return dict(as_of=as_of.isoformat(),windows=windows, complete_weeks_6=complete_weeks(conn,6,as_of=as_of),recent_runs_42=recent,
                quality_history=dict(status='not_classified_from_titles_or_venue',lap_covered_runs=sum(x['lap_status']=='verified' for x in recent)),
                weekly_distance_m=windows['rolling_28']['distance_m']/4 if windows['rolling_28']['distance_m'] is not None else None,
                weekly_timer_s=windows['rolling_28']['timer_s']/4 if windows['rolling_28']['timer_s'] is not None else None,
                recent_long_exposures=recent_long,
                definition='28 saved calendar days / 4; unrecorded activity and excluded time remain unknown')


def rest(day, reason, kind='rest'):
    return dict(date=day, type=kind, target_duration_s=0, target_distance_m=0,
                intensity='不安排跑步强度', steps=[], conditional_on_symptom_check=False,
                pace_reference=None, reason=reason)


def easy(day, seconds, recovery, references):
    kind = 'recovery_run' if recovery else 'easy_run'
    edge = min(300, seconds//4)
    return dict(date=day, type=kind, target_duration_s=seconds, target_distance_m=None,
                intensity='能完整交谈的轻松程度；不设未经确认的阈值',
                steps=[dict(phase='warmup', duration_s=edge, description='渐进进入轻松状态'),
                       dict(phase='main', duration_s=seconds-edge*2, description='保持轻松；不适时停止本次安排并反馈'),
                       dict(phase='cooldown', duration_s=edge, description='轻松放缓')],
                conditional_on_symptom_check=True,
                pace_reference=next((deepcopy(r) for r in references if r['metric']=='easy_pace_s_km' and r['basis']=='user_confirmed'), None),
                reason='长距离后保守恢复窗口' if recovery else '依据既有训练基础的低强度起步周')


def initial_plan(profile, basis, start, as_of, *,program='auto'):
    if program=='marathon' or (program=='auto' and profile.get('plan_program')=='marathon'):
        return marathon_plan(profile,basis,start,as_of)
    return recovery_plan_v1(profile,basis,start,as_of)


def recovery_plan_v1(profile, basis, start, as_of):
    if start <= as_of:
        raise CoreError('PLAN_START_MUST_BE_FUTURE')
    missing = []
    weekdays = profile['training_weekdays']
    if not weekdays:
        missing.append('confirmed_training_weekdays')
    goals = profile['goals']
    if not goals or not any(g['date'] or g['date_window'] for g in goals):
        missing.append('dated_goal_or_explicit_date_window')
    if not basis['windows']['rolling_28']['running_days'] or not basis['weekly_timer_s']:
        missing.append('reliable_recent_training_time')
    if missing:
        return dict(status='needs_information', missing=missing, sessions=[], rule_version=RULE_VERSION)
    seconds = int(min(2700, basis['weekly_timer_s']*.8/len(weekdays))//300)*300
    sessions, reasons = [], []
    for offset in range(7):
        day = start+timedelta(days=offset)
        recovery = any(0 <= (day-date.fromisoformat(x['date'])).days < 14 for x in basis['recent_long_exposures'])
        first_days = any(0 <= (day-date.fromisoformat(x['date'])).days <= 3 for x in basis['recent_long_exposures'])
        event = next((g for g in goals if g['date']==day.isoformat()), None)
        if event:
            sessions.append(rest(day.isoformat(), '已确认目标日；尚未形成赛事执行处方，需单独核对距离、恢复和参赛决定', 'race_review'))
        elif day.weekday() not in weekdays:
            sessions.append(rest(day.isoformat(), '本人可训练日以外'))
        elif first_days:
            sessions.append(rest(day.isoformat(), '近期长距离暴露后的前三个日历日，保守暂不安排跑步'))
        elif seconds < 600:
            sessions.append(rest(day.isoformat(), '可用时长基线不足以安排本轮最小跑步单元', 'review'))
        else:
            sessions.append(easy(day.isoformat(), min(seconds,1200) if recovery else seconds, recovery, profile['reference_ranges']))
    if profile['current_symptoms'] is None:
        reasons.append('当前症状未报告；每次跑步均以开跑前本人复核为条件，不解释为无症状。')
    if profile['current_symptoms']:
        sessions = [rest(x['date'], '档案有局部症状，暂缓结构化跑步，待状态更新后重新评估', 'review') if x['target_duration_s'] else x for x in sessions]
        reasons.append('已报告症状触发保守安排；未作医学诊断。')
    reasons += ['所有时长包含热身/主训练/放松；距离未规定时为null，不能从假配速倒推。',
                '采用28天有效时长均值的80%起步上限、单次45分钟上限；距最近30km以上暴露14天内单次最多20分钟且不排强度。这些是可审计工程规则，不是恢复天数或安全性的医学保证。',
                '目标日期窗口原样保留；未推定比赛距离、12月某一天、目标成绩或生理阈值。',
                '当前版本只生成保守恢复/轻松周，不是完整马拉松周期化处方。']
    result = dict(validation_status='passed_conservative_rules', rule_version=RULE_VERSION,
                  start=start.isoformat(), end=(start+timedelta(days=6)).isoformat(), goals=deepcopy(goals),
                  sessions=sessions, requested_training_days=len(weekdays),
                  scheduled_running_days=sum(x['type'] in {'easy_run','recovery_run'} for x in sessions),
                  total_target_duration_s=sum(x['target_duration_s'] for x in sessions),
                  training_basis=basis, limitations=reasons)
    validate_plan(result, profile)
    return result


def validate_plan(plan, profile):
    if plan.get('program')=='marathon':return validate_marathon(plan,profile)
    if plan.get('validation_status') != 'passed_conservative_rules':
        raise CoreError('PLAN_NOT_READY')
    sessions = plan['sessions']
    dates = [date.fromisoformat(x['date']) for x in sessions]
    if len(dates)!=7 or any(day != dates[0]+timedelta(days=i) for i,day in enumerate(dates)):
        raise CoreError('PLAN_DATES_INVALID')
    runs = 0
    for day, item in zip(dates, sessions):
        if item['type'] not in {'rest','review','race_review','easy_run','recovery_run'}:
            raise CoreError('UNSUPPORTED_INTENSITY')
        duration = item['target_duration_s']
        if type(duration) is not int or not 0 <= duration <= 2700:
            raise CoreError('PLAN_DURATION_INVALID')
        if item['type'] in {'easy_run','recovery_run'}:
            runs += 1
            if day.weekday() not in profile['training_weekdays'] or duration < 600:
                raise CoreError('AVAILABILITY_OR_DURATION_INVALID')
            if sum(x['duration_s'] for x in item['steps']) != duration or len(item['steps'])!=3:
                raise CoreError('SESSION_PHASES_INVALID')
        elif duration != 0 or item['steps']:
            raise CoreError('REST_PRESCRIPTION_INVALID')
    if runs > len(profile['training_weekdays']):
        raise CoreError('TOO_MANY_TRAINING_DAYS')
    if sum(x['target_duration_s'] for x in sessions) > plan['training_basis']['weekly_timer_s']*.8 + 1:
        raise CoreError('BASELINE_VOLUME_LIMIT')


def adjusted_plan(original, feedback, *, as_of, days, recent_long_exposures=(),execution=None,training_basis=None):
    if original.get('program')=='marathon':
        return adjust_marathon(original,feedback,as_of=as_of,days=days,execution=execution,training_basis=training_basis)
    if type(days) is not int or not 3 <= days <= 7:
        raise CoreError('ADJUSTMENT_WINDOW_INVALID')
    candidate = deepcopy(original)
    symptoms = feedback['symptoms']
    local_symptom = bool(symptoms and any(x['kind'] in {'pain','cramp_warning'} for x in symptoms))
    repeated = bool(symptoms and any(x.get('persistent') or x.get('recurring') for x in symptoms))
    high_fatigue = feedback['fatigue']=='high' or (feedback['rpe'] is not None and feedback['rpe']>=8)
    if local_symptom:
        action = 'defer_running_for_review'
        reason = '局部疼痛/抽筋前兆已报告；不升级强度，暂缓窗口内结构化跑步并等待本人复核。' + ('存在持续或反复报告。' if repeated else '')
    elif high_fatigue:
        action = 'reduce_duration'
        reason = '高疲劳或RPE>=8，窗口内现有跑步时长按60%保守下调；不是恢复百分比。'
    else:
        action = 'keep_plan'
        reason = '无明确减量触发，保持计划；单次RPE4不加量，未填症状仍是未知。'
    end = as_of+timedelta(days=days)
    differences = []
    for index, old in enumerate(original['sessions']):
        day = date.fromisoformat(old['date'])
        if not as_of < day <= end or old['type'] not in {'easy_run','recovery_run'}:
            continue
        if local_symptom:
            new = rest(old['date'], reason, 'review')
        elif high_fatigue:
            duration = int(old['target_duration_s']*.6//60)*60
            new = easy(old['date'], duration, True, []) if duration>=600 else rest(old['date'], reason, 'review')
            new['reason'] = reason
        elif any(0 <= (day-date.fromisoformat(x['date'])).days <= 3 for x in recent_long_exposures):
            new = rest(old['date'], '新增真实长距离暴露触发前三日保守复核', 'review')
        elif old['target_duration_s']>1200 and any(0 <= (day-date.fromisoformat(x['date'])).days < 14 for x in recent_long_exposures):
            new = easy(old['date'], 1200, True, [])
            new['reason'] = '依据当前已保存长距离暴露，将窗口内现有跑步限制到20分钟恢复安排'
        else:continue
        # Combine, rather than bypass, objective recovery guards and subjective fatigue.
        if not local_symptom and any(0 <= (day-date.fromisoformat(x['date'])).days <= 3 for x in recent_long_exposures):
            new = rest(old['date'], '新增真实长距离暴露触发前三日保守复核', 'review')
        elif new['target_duration_s']>1200 and any(0 <= (day-date.fromisoformat(x['date'])).days < 14 for x in recent_long_exposures):
            new = easy(old['date'],1200,True,[])
            new['reason'] = '疲劳减量与真实长距离恢复上限共同校验'
        candidate['sessions'][index] = new
        differences.append(dict(date=old['date'], before=deepcopy(old), after=deepcopy(new), reason=new['reason']))
    if differences and not local_symptom and not high_fatigue:
        action, reason = 'apply_new_long_exposure_guard', '当前真实长距离证据触发保守恢复限制；没有加量。'
    candidate['scheduled_running_days'] = sum(x['type'] in {'easy_run','recovery_run'} for x in candidate['sessions'])
    candidate['total_target_duration_s'] = sum(x['target_duration_s'] for x in candidate['sessions'])
    return dict(action=action, reason=reason, adjustment_start=(as_of+timedelta(days=1)).isoformat(),
                adjustment_end=end.isoformat(), diff=differences, suggested_plan=candidate,
                missing_feedback=[k for k in ('rpe','fatigue','symptoms') if feedback[k] is None])


def goal_bounds(goal):
    if goal.get('date'):
        day=date.fromisoformat(goal['date']);return day,day
    if goal.get('date_range'):
        return date.fromisoformat(goal['date_range']['start']),date.fromisoformat(goal['date_range']['end'])
    return None


def floor_distance(value):return int(max(0,value)//500)*500


def phase_at(days):
    if days<0:return 'after_target'
    if days<=6:return 'race_week'
    if days<=13:return 'taper_late'
    if days<=20:return 'taper_early'
    if days<=56:return 'marathon_specific'
    return 'base'


PHASE_FACTORS={'base':(.85,1.0),'marathon_specific':(.85,1.0),'taper_early':(.65,.8),
               'taper_late':(.45,.65),'race_week':(.2,.35),'after_target':(0,.25)}


def distance_session(day,distance,kind,profile,reason):
    if kind=='steady':
        warm=2000;cool=1500;work=distance-warm-cool-1000
        # Three controlled bouts, two 500m easy recoveries; every metre accounted.
        first=work//3;parts=[first,first,work-first*2]
        steps=[dict(phase='warmup',distance_m=warm,description='轻松渐进热身')]
        for i,part in enumerate(parts):
            steps.append(dict(phase='main',distance_m=part,description='可控稳态，不强行追目标马配',rpe_range=[5,6]))
            if i<2:steps.append(dict(phase='recovery',distance_m=500,description='轻松慢跑恢复'))
        steps.append(dict(phase='cooldown',distance_m=cool,description='轻松放松'))
        intensity='可控稳态RPE5–6参考；不等同已测阈值，不使用目标成绩硬定配速'
    else:
        edge=min(1000,distance//4)
        steps=[dict(phase='warmup',distance_m=edge,description='轻松进入状态'),
               dict(phase='main',distance_m=distance-edge*2,description='保持可完整交谈，长跑亦不加速冲刺'),
               dict(phase='cooldown',distance_m=edge,description='轻松放缓')]
        intensity='轻松有氧，以完整交谈和主观控制为准；无已测阈值处方'
    reference=next((deepcopy(x) for x in profile['reference_ranges'] if x['metric']=='easy_pace_s_km' and x['basis']=='user_confirmed'),None) if kind!='steady' else None
    duration_range=[distance*reference['lower']/1000,distance*reference['upper']/1000] if reference else None
    return dict(date=day,type=kind,target_distance_m=distance,target_duration_s=None,duration_range_s=duration_range,
                intensity=intensity,steps=steps,conditional_on_symptom_check=True,pace_reference=reference,
                intensity_source='user_confirmed_easy_reference' if reference else 'explicit_subjective_control_not_physiological_measurement',reason=reason)


def readiness(profile,basis,as_of):
    status=profile.get('training_status',{})
    symptoms=profile['current_symptoms']
    races=[x for x in basis['recent_runs_42'] if x['distance_m'] is not None and x['distance_m']>=40000]
    race=max(races,key=lambda x:x['local_date']) if races else None
    assessed=date.fromisoformat(status['assessment_date']) if status.get('assessment_date') else None
    fresh=assessed is not None and 0<=(as_of-assessed).days<=7
    ready=(fresh and status.get('recovery')=='ready' and status.get('daily_function_normal') is True and
           status.get('easy_run_tolerated') is True and symptoms==[])
    after_race_short=[x for x in basis['recent_runs_42'] if race and x['local_date']>race['local_date'] and x['distance_m'] and x['distance_m']<=10000]
    race_released=bool(race and (as_of-date.fromisoformat(race['local_date'])).days>=7 and ready and len(after_race_short)>=2)
    recovering=bool((race and not race_released) or (status.get('mode')=='post_race_recovery' and not ready))
    return dict(ready=ready,recovering=recovering,assessment_fresh=fresh,recent_full_distance_exposure=race,
                race_released=race_released,post_exposure_short_sessions=len(after_race_short),
                release_conditions=['本人近期确认日常活动正常','当前明确无局部症状','本人确认短轻松跑可耐受',
                                    '全马暴露后至少两条可核查的短距离记录；其轻松程度仍需本人反馈','时间底限不是自动解除条件'])


def marathon_plan(profile,basis,start,as_of):
    if start<=as_of:raise CoreError('PLAN_START_MUST_BE_FUTURE')
    status=readiness(profile,basis,as_of)
    missing=[];weekdays=profile['training_weekdays']
    if not weekdays:missing.append('confirmed_training_weekdays')
    if not profile.get('training_status'):missing.append('current_training_and_recovery_status')
    elif not status['assessment_fresh']:missing.append('fresh_training_status_assessment')
    weeks=basis['complete_weeks_6']
    observed=[x for x in weeks[-4:] if x['distance_m'] is not None]
    if len([x for x in weeks if x['running_days']])<4 or not basis['weekly_distance_m']:missing.append('four_weeks_reliable_running_basis')
    goals=[g for g in profile['goals'] if g['role']=='A' and g['distance_m']==42195 and (goal_bounds(g) is None or goal_bounds(g)[1]>=start)]
    goal=next((g for g in goals if goal_bounds(g)),None)
    if not status['recovering']:
        if goal is None:missing.append('A_marathon_date_or_explicit_date_range')
        if profile['current_symptoms'] is None:missing.append('explicit_current_symptom_report')
        if not status['ready']:missing.append('confirmed_current_recovery_readiness')
    if missing:return dict(status='needs_confirmation',missing=list(dict.fromkeys(missing)),sessions=[])
    base=min(basis['weekly_distance_m'],median(x['distance_m'] for x in observed))
    if base<=0:return dict(status='needs_confirmation',missing=['positive_running_volume_basis'],sessions=[])
    observed_days=median(x['running_days'] for x in observed)
    if len(weekdays)>observed_days+1:return dict(status='needs_confirmation',missing=['training_frequency_increase_confirmation'],sessions=[])
    capacity_long=max((x['distance_m'] for x in basis['recent_runs_42'] if x['distance_m'] and x['distance_m']<40000),default=0)
    bounds=goal_bounds(goal) if goal else None
    frames=[]
    for i in range(4):
        begin=start+timedelta(days=7*i);end=begin+timedelta(days=6)
        days_range=[(bounds[0]-begin).days,(bounds[1]-begin).days] if bounds else None
        phases=sorted({phase_at(d) for d in range(days_range[0],days_range[1]+1)}) if days_range else []
        phase=phases[0] if len(phases)==1 else 'conditional_transition'
        if status['recovering']:
            phase='post_race_recovery' if i==0 else 'conditional_rebuild'
            factors=(0,.3 if i==0 else .5)
        else:
            factors=(min(PHASE_FACTORS[x][0] for x in phases),min(PHASE_FACTORS[x][1] for x in phases))
        events=[dict(event=g['event'],date=g['date'],role=g['role'],distance_m=g['distance_m']) for g in profile['goals'] if g['date'] and begin.isoformat()<=g['date']<=end.isoformat()]
        if events and not status['recovering']:factors=(factors[0]*.75,factors[1]*.8)
        frames.append(dict(week=i+1,start=begin.isoformat(),end=end.isoformat(),phase=phase,possible_phases=phases,
            days_to_A_range=days_range,goal_date_exact=goal['date'] if goal else None,goal_date_range=goal.get('date_range') if goal else None,
            purpose='恢复观察，条件未满足不自动进阶' if status['recovering'] else '有氧、可控专项与长跑平衡；按比赛窗口减量',
            planned_training_days_range=[0,len(weekdays)] if status['recovering'] else [len(weekdays),len(weekdays)],
            proposed_distance_range_m=[floor_distance(base*factors[0]),floor_distance(base*factors[1])],
            quality_types=[] if status['recovering'] or base<30000 or len(weekdays)<4 or not set(phases)<={'base','marathon_specific','taper_early'} else ['event_review_replaces_extra_quality'] if events else ['controlled_steady_if_ready'],
            long_run_limit_m=0 if status['recovering'] else floor_distance(min(capacity_long,32000,base*factors[1]*.4)),
            events=events,volume_excludes_race=True,conditional=True,
            conditions=status['release_conditions'] if status['recovering'] else ['每周重新读取实际完成和主观反馈；无依据不自动加量']))
    sessions=[];limitations=[]
    if status['recovering']:
        for offset in range(7):
            day=start+timedelta(days=offset)
            sessions.append(rest(day.isoformat(),'赛后恢复条件未满足，休息/复核；不得因超过固定天数自动排强度','review' if day.weekday() in weekdays else 'rest'))
        mode='post_race_recovery'
    else:
        mode='normal_preparation' if base>=30000 and len(weekdays)>=4 else 'base_limited'
        target=floor_distance(base*min(.95,frames[0]['proposed_distance_range_m'][1]/base))
        days=[start+timedelta(days=i) for i in range(7) if (start+timedelta(days=i)).weekday() in weekdays]
        long_day=days[-1]
        last_long=max((date.fromisoformat(x['local_date']) for x in basis['recent_runs_42'] if x['distance_m'] and x['distance_m']>=16000),default=as_of-timedelta(days=30))
        # 3 calendar days avoids promising an exact 48h gap from unknown planned start times.
        quality_candidates=[d for d in days if (long_day-d).days>=3 and (d-last_long).days>=3 and bounds and
            all(phase_at(x) in {'base','marathon_specific','taper_early'} for x in range((bounds[0]-d).days,(bounds[1]-d).days+1))]
        quality_day=quality_candidates[0] if mode=='normal_preparation' and quality_candidates and set(frames[0]['possible_phases'])<={'base','marathon_specific','taper_early'} else None
        near_events=[g for g in profile['goals'] if g['date'] and start.isoformat()<=g['date']<=(start+timedelta(days=6)).isoformat()]
        if near_events:quality_day=None;limitations.append('本周有目标赛事，取消额外稳态课；赛事执行须单独确认，未当作已完成负荷。')
        long_phase_cap=min(PHASE_FACTORS[phase_at(x)][1] for x in range((bounds[0]-long_day).days,(bounds[1]-long_day).days+1))
        long_m=floor_distance(min(capacity_long,frames[0]['long_run_limit_m'],target*.4,base*long_phase_cap*.4))
        quality_m=10500 if target>=50000 else 7500
        if quality_day and target-long_m-quality_m<2000*(len(days)-2):quality_day=None
        allocated={long_day:long_m}
        if quality_day:allocated[quality_day]=quality_m
        other=[d for d in days if d not in allocated]
        remaining=target-sum(allocated.values())
        for i,d in enumerate(other):
            value=floor_distance(remaining/(len(other)-i));allocated[d]=value;remaining-=value
        for i in range(7):
            day=start+timedelta(days=i)
            event=next((g for g in near_events if g['date']==day.isoformat()),None)
            if event:sessions.append(rest(day.isoformat(),'目标赛事日：仅待本人确认执行，不编造比赛处方','race_review'))
            elif day not in allocated:sessions.append(rest(day.isoformat(),'档案指定休息/不可训练日'))
            elif allocated[day]<1500:sessions.append(rest(day.isoformat(),'当前基础不足以分配可执行跑步单元','review'))
            else:
                kind='steady' if day==quality_day else 'long_run' if day==long_day else 'easy_run'
                if near_events and kind=='long_run':kind='easy_run';allocated[day]=min(allocated[day],5000)
                sessions.append(distance_session(day.isoformat(),allocated[day],kind,profile,
                    '依据最近4–6周真实跑量/频率及实际长跑上限分配；目标成绩不作为已验证配速'))
        if quality_day is None:limitations.append('稳态课门槛/间隔或赛事约束未满足，本周不额外安排质量课。')
        if mode=='base_limited':limitations.append('基础受限，仅建立低强度规律；未验证当前马拉松目标可达性。')
    plan=dict(program='marathon',rule_version=RULE_VERSION,mode=mode,validation_status='passed_conservative_rules',
        start=start.isoformat(),end=(start+timedelta(days=6)).isoformat(),goals=deepcopy(profile['goals']),
        sessions=sessions,framework_4_weeks=frames,requested_training_days=len(weekdays),
        scheduled_running_days=sum(x['type'] in {'easy_run','long_run','steady','recovery_run'} for x in sessions),
        total_target_distance_m=sum(x['target_distance_m'] for x in sessions),
        total_target_duration_s=0 if mode=='post_race_recovery' else None,
        training_basis=basis,capacity=dict(weekly_base_m=base,long_run_demonstrated_m=capacity_long,observed_running_days=observed_days),
        readiness=status,goal_pace_is_prescription=False,
        target_pace_aspiration_s_km=goal['target_time_s']*1000/42195 if goal and goal['target_time_s'] else None,
        limitations=limitations+['四周是条件性框架，不是已批准的未来28天正式课表。','配速能力、阈值、质量课完成历史未充分标注时不推定；RPE描述为控制方式，不是生理实测。',
            '全马以外专项未在本轮验收；规则是工程保守边界，不是医学恢复或安全保证。'])
    validate_marathon(plan,profile)
    plan['validation_results']=['seven_dates','availability_and_rest','session_distance_sum','weekly_volume_cap','quality_spacing','demonstrated_long_run_cap','no_goal_pace_as_capacity']
    return plan


def validate_marathon(plan,profile):
    frames=plan['framework_4_weeks']
    if len(frames)!=4:raise CoreError('FOUR_WEEK_FRAMEWORK_REQUIRED')
    for index,frame in enumerate(frames):
        expected=date.fromisoformat(plan['start'])+timedelta(days=index*7)
        low,high=frame['proposed_distance_range_m']
        if frame['start']!=expected.isoformat() or frame['end']!=(expected+timedelta(days=6)).isoformat():raise CoreError('FRAMEWORK_DATES_INVALID')
        if not 0<=low<=high<=plan['capacity']['weekly_base_m']:raise CoreError('FRAMEWORK_VOLUME_INVALID')
    dates=[date.fromisoformat(x['date']) for x in plan['sessions']]
    if len(dates)!=7 or any(d!=dates[0]+timedelta(days=i) for i,d in enumerate(dates)):raise CoreError('PLAN_DATES_INVALID')
    hard=[];long=[];distance=0;count=0
    for day,s in zip(dates,plan['sessions']):
        if s['type'] in {'rest','review','race_review'}:
            if s['target_distance_m']!=0 or s['target_duration_s']!=0 or s['steps']:raise CoreError('REST_PRESCRIPTION_INVALID')
            continue
        if s['type'] not in {'easy_run','steady','long_run','recovery_run'}:raise CoreError('UNSUPPORTED_INTENSITY')
        if day.weekday() not in profile['training_weekdays'] or day.weekday() in profile.get('rest_weekdays',[]):raise CoreError('AVAILABILITY_OR_DURATION_INVALID')
        d=s['target_distance_m']
        if type(d) is not int or d<1500 or sum(x.get('distance_m',0) for x in s['steps'])!=d:raise CoreError('SESSION_DISTANCE_INVALID')
        if any(type(x.get('distance_m')) is not int or x['distance_m']<=0 for x in s['steps']):raise CoreError('SESSION_PHASES_INVALID')
        if s['steps'][0]['phase']!='warmup' or s['steps'][-1]['phase']!='cooldown':raise CoreError('SESSION_PHASES_INVALID')
        if s['type']=='steady':
            hard.append(day)
            if not any(x['phase']=='recovery' for x in s['steps']):raise CoreError('QUALITY_RECOVERY_MISSING')
        if s['type']=='long_run':
            long.append(day)
            if d>min(plan['capacity']['long_run_demonstrated_m'],32000,plan['capacity']['weekly_base_m']*.4):raise CoreError('LONG_RUN_CAP')
        if s['target_duration_s'] is not None:raise CoreError('UNSUPPORTED_FAKE_PRECISE_DURATION')
        distance+=d;count+=1
    if len(hard)>1 or any(abs((a-b).days)<3 for a in hard for b in long):raise CoreError('QUALITY_SPACING_INVALID')
    if count>len(profile['training_weekdays']) or distance>plan['capacity']['weekly_base_m']+1:raise CoreError('BASELINE_VOLUME_LIMIT')
    if count!=plan['scheduled_running_days']:raise CoreError('RUNNING_DAY_TOTAL_MISMATCH')
    if distance!=plan['total_target_distance_m']:raise CoreError('PLAN_TOTAL_MISMATCH')
    if plan['mode']=='post_race_recovery' and (hard or long):raise CoreError('RECOVERY_INTENSITY_FORBIDDEN')


def adjust_marathon(original,feedback,*,as_of,days,execution=None,training_basis=None):
    if type(days) is not int or not 3<=days<=7:raise CoreError('ADJUSTMENT_WINDOW_INVALID')
    result=deepcopy(original);symptoms=feedback['symptoms']
    pain=bool(symptoms and any(x['kind'] in {'pain','cramp_warning','limping','severe_symptom'} for x in symptoms))
    severe=bool(symptoms and any(x['kind'] in {'limping','severe_symptom'} or x.get('persistent') or x.get('severity',0)>=7 for x in symptoms))
    fatigued=feedback['fatigue']=='high' or (feedback['rpe'] is not None and feedback['rpe']>=8) or feedback.get('next_day_recovery')=='poor'
    overshoot=bool(execution and execution.get('identity_match')=='single_day_activity_volume_only' and execution.get('planned_target_distance_m') and execution.get('actual_day',{}).get('distance_m',0)>execution['planned_target_distance_m']*1.25)
    original_cutoff=original['training_basis'].get('as_of',(date.fromisoformat(original['start'])-timedelta(days=1)).isoformat())
    new_full=[x for x in (training_basis or {}).get('recent_runs_42',[]) if x.get('distance_m') and x['distance_m']>=40000 and original_cutoff<x['local_date']<=as_of.isoformat()]
    post_full=bool(new_full)
    reason='新出现全马级距离暴露，暂缓未来跑步并重新确认恢复状态' if post_full else '局部症状触发复核，暂缓结构化训练' if pain else '主观恢复差/高疲劳或实际完成量超出计划，降低后续负荷' if fatigued or overshoot else '无明确减量依据，保留；缺反馈不视为恢复良好，RPE4不加量'
    diff=[]
    for i,old in enumerate(original['sessions']):
        day=date.fromisoformat(old['date'])
        if not as_of<day<=as_of+timedelta(days=days) or old['type'] in {'rest','review','race_review'}:continue
        if pain or post_full:new=rest(old['date'],reason,'review')
        elif fatigued or overshoot:
            d=floor_distance(old['target_distance_m']*.6)
            if d<1500:new=rest(old['date'],reason,'review')
            else:new=distance_session(old['date'],d,'easy_run',dict(reference_ranges=[]),reason)
        else:continue
        result['sessions'][i]=new;diff.append(dict(date=old['date'],before=deepcopy(old),after=deepcopy(new),reason=reason))
    result['total_target_distance_m']=sum(x['target_distance_m'] for x in result['sessions'])
    result['framework_4_weeks'][0]['detail_after_proposal_m']=result['total_target_distance_m']
    result['framework_4_weeks'][0]['note']='原框架区间保留作为先前条件性建议；具体七日安排以本次待确认diff为准。'
    result['scheduled_running_days']=sum(x['type'] not in {'rest','review','race_review'} for x in result['sessions'])
    return dict(action='defer_running_for_review' if pain or post_full else 'reduce_load' if diff else 'keep_plan',reason=reason,diff=diff,suggested_plan=result,
        triggers=dict(local_symptoms=pain,poor_recovery_or_high_effort=fatigued,distance_overshoot=overshoot,new_full_distance_exposure=post_full),
        adjustment_start=(as_of+timedelta(days=1)).isoformat(),adjustment_end=(as_of+timedelta(days=days)).isoformat(),
        formal_coverage_end=original['end'],medical_review_notice='持续疼痛、跛行或严重症状应寻求医学评估；本工具不作诊断。' if severe else None,
        missing_feedback=[k for k in ['rpe','fatigue','symptoms','next_day_recovery'] if feedback.get(k) is None or feedback.get(k)=='unknown'])
