"""ActivityAnalysis: reuse M1 eligible metrics and real laps, strictly offline."""
from datetime import date, timedelta
import math

from . import wb_reports
from .queries import rolling_stats, complete_weeks, period_stats, today_local
from .core_schema import SCHEMA_VERSION, RULE_VERSION, CoreError
from .storage import utc_now


def usable(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def history(conn, as_of=None):
    end = as_of or today_local()
    periods = dict(rolling_7=rolling_stats(conn, 7, as_of=end),
                   rolling_28=rolling_stats(conn, 28, as_of=end),
                   complete_natural_weeks=complete_weeks(conn, 4, as_of=end),
                   current_week_to_date=period_stats(conn, end-timedelta(days=end.weekday()), end))
    for item in [periods['rolling_7'], periods['rolling_28'], periods['current_week_to_date'], *periods['complete_natural_weeks']]:
        item['evidence_activity_ids'] = [row[0] for row in conn.execute(
            "SELECT id FROM activity WHERE count_status='counted' AND kind IN ('running','track_running') AND local_date BETWEEN ? AND ? ORDER BY id",
            (item['start'], item['end']))]
    return dict(as_of=end.isoformat(), timezone='Asia/Shanghai',
                load_definition='objective distance/time exposure, not TSS, physiological fatigue or injury probability', **periods)


def envelope(conn):
    meta = wb_reports.metadata(conn)
    return dict(schema_version=SCHEMA_VERSION, rule_version=RULE_VERSION, generated_at_utc=utc_now(),
                data_as_of=dict(last_successful_sync_at_utc=meta['last_successful_sync_at_utc'],
                                latest_activity_at_local=meta['latest_activity_at_local']),
                source=dict(kind='local_m1_sqlite', region='garmin.cn', data_version=meta['data_version'],
                            network_refresh=False), evidence_refs=[], limitations=[])


def safe_summary(conn, activity_id):
    item = wb_reports.summary(conn, activity_id)
    facts = dict(item['facts'])
    for metric, policy in item['metric_quality'].items():
        if metric in facts and (policy['status'] != 'included' or not usable(facts[metric])):
            facts[metric] = None
    for metric in ('avg_hr_bpm', 'max_hr_bpm'):
        if facts[metric] == 0:
            facts[metric] = None
    return facts, item


class ActivityAnalysis:
    def __init__(self, instance):
        self.instance = instance

    def analyze(self, activity_id='latest', *, as_of=None):
        with self.instance.database() as conn:
            try:
                facts, original = safe_summary(conn, activity_id)
            except ValueError:
                raise CoreError('ACTIVITY_NOT_FOUND_OR_INVALID_ID') from None
            report = wb_reports.report(conn, facts['id'])
            source_row = conn.execute('SELECT provider,region,provider_activity_id,started_at_utc,timezone_basis FROM activity WHERE id=?', (facts['id'],)).fetchone()
            facts['started_at_utc'] = source_row['started_at_utc']
            laps = report['laps']
            for lap in laps['rows']:
                if 'average_hr_exceeds_maximum_hr' in lap['quality_flags']:
                    lap['avg_hr_bpm'] = lap['max_hr_bpm'] = None
                if 'duration_order_conflict' in lap['quality_flags']:
                    lap['timer_s'] = lap['moving_s'] = lap['elapsed_s'] = None
            end = as_of or today_local()
            latest_date = date.fromisoformat(facts['local_date']) if facts['local_date'] else None
            historical = history(conn, end)
            activity_windows = history(conn, latest_date) if latest_date else None
            comparisons = []
            distance = facts['distance_m']
            if distance and facts['kind'] in {'running', 'track_running'}:
                candidates = conn.execute(
                    "SELECT id FROM activity WHERE count_status='counted' AND kind IN ('running','track_running') AND started_at_utc < (SELECT started_at_utc FROM activity WHERE id=?) AND distance_m BETWEEN ? AND ? ORDER BY abs(distance_m-?),started_at_utc DESC LIMIT 15",
                    (facts['id'], distance*.8, distance*1.2, distance)).fetchall()
                for candidate in candidates:
                    similar, raw = safe_summary(conn, candidate[0])
                    if similar['distance_m'] is None or raw['calculations']['timer_pace_s_per_km'] is None:
                        continue
                    pace = original['calculations']['timer_pace_s_per_km']
                    comparisons.append(dict(activity_id=similar['id'], date=similar['local_date'],
                                            distance_m=similar['distance_m'], timer_s=similar['timer_s'],
                                            avg_hr_bpm=similar['avg_hr_bpm'], type_key=similar['type_key'],
                                            timer_pace_s_km=raw['calculations']['timer_pace_s_per_km'],
                                            pace_difference_s_km=pace-raw['calculations']['timer_pace_s_per_km'] if pace is not None else None))
                    if len(comparisons) == 3:
                        break
            limits = ['没有天气、海拔/场地条件、传感器一致性或心率时序，配速差不能单独证明体能进退。',
                      '计时器/移动/经过时长分开；字段隔离不否定可靠距离。',
                      '7/28天负荷仅为已保存距离和有效时长；无TSS、HRV、生理疲劳百分比。',
                      '未联网刷新；未保存活动不等于没有训练。',
                      '活动标题不作为训练结构或计划完成的证据。']
            missing = ['weather', 'terrain', 'sensor_comparability', 'heart_rate_time_series', 'confirmed_thresholds', 'current_symptoms']
            if not laps['rows']:
                missing.append('real_laps_not_obtained')
            for metric in ('distance_m', 'timer_s', 'moving_s', 'elapsed_s', 'avg_hr_bpm', 'max_hr_bpm'):
                if facts[metric] is None:
                    missing.append(metric)
            high_load = bool(distance and distance >= 30000)
            inference = [dict(text='这是已保存的长距离训练暴露，后续计划应先复核恢复状态。', basis='distance_m >= 30000; conservative scheduling guard, not a medical threshold', confidence='limited')] if high_load else []
            result = envelope(conn)
            result.update(activity_source=dict(source_row), facts=facts,
                          metric_quality=original['metric_quality'], source_metric_values={k:original['facts'].get(k) for k in original['metric_quality']},
                          calculations=original['calculations'], real_laps=laps, history=historical,
                          history_at_activity=activity_windows, historical_comparisons=comparisons,
                          inferences=inference, missing=missing,
                          recommendations=[dict(text='下一堂先核对主观疲劳和局部症状；资料不足时只考虑恢复/轻松安排，不据配速自动升级强度。',
                                                status='advice_not_a_saved_plan', basis='available facts and missing feedback')],
                          plan_comparison=dict(status='尚未建立计划'),
                          quality_issues=report['quality_issues'], evidence_refs=[dict(activity_id=facts['id'], revision=facts['revision']), *[dict(activity_id=x['activity_id']) for x in comparisons]],
                          limitations=limits)
            return result


def markdown(report):
    facts = report['facts']
    pace = report['calculations']['timer_pace_s_per_km']
    return '\n'.join([
        '# RunWise 训练报告', '',
        '规则：' + report['rule_version'],
        '## 客观事实', '',
        '- 本地活动：%s；时间：%s（Asia/Shanghai）' % (facts['id'], facts['started_at_local']),
        '- 距离：%s m；计时器/移动/经过：%s / %s / %s 秒' % (facts['distance_m'], facts['timer_s'], facts['moving_s'], facts['elapsed_s']),
        '- 平均/最大心率：%s / %s bpm；真实圈：%s（%s）' % (facts['avg_hr_bpm'], facts['max_hr_bpm'], report['real_laps']['count'], report['real_laps']['status']),
        '', '## 程序计算', '', '- 计时器平均配速：%s 秒/公里' % (round(pace, 3) if pace is not None else '不可用'),
        '- 最近7/28天跑量：%s / %s km' % (report['history']['rolling_7']['distance_km'], report['history']['rolling_28']['distance_km']),
        '', '## 谨慎推断', '', *['- '+x['text'] for x in report['inferences']],
        '', '## 缺失与限制', '', *['- '+x for x in report['limitations']], '- 缺失字段：'+', '.join(report['missing']),
        '', '## 建议', '', *['- '+x['text'] for x in report['recommendations']],
        '- 计划对照：'+report['plan_comparison']['status'], '',
    ])
