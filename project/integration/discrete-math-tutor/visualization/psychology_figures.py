"""受控心理学示意图：所有概率和曲线来自同一等方差正态模型。"""
import math
from statistics import NormalDist


def signal_figure(spec):
    if set(spec) != {'phase', 'd_prime', 'criterion'}:
        raise ValueError('信号检测参数字段无效')
    phase, d_prime, criterion = spec['phase'], spec['d_prime'], spec['criterion']
    if type(phase) is not int or not 0 <= phase <= 5:
        raise ValueError('信号检测阶段无效')
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (d_prime, criterion)):
        raise ValueError('信号检测参数必须为有限数值')
    if not 0 < d_prime <= 3 or not -2 <= criterion <= 3:
        raise ValueError('信号检测参数超出示意范围')
    noise, signal = NormalDist(), NormalDist(d_prime, 1)
    hit, false_alarm = 1 - signal.cdf(criterion), 1 - noise.cdf(criterion)
    x = lambda value: 42 + (value + 3.5) / 9 * 450
    y = lambda value: 164 - value * 300

    def path(points):
        return ' '.join(('M' if i == 0 else 'L') + f'{a:.2f},{b:.2f}'
                        for i, (a, b) in enumerate(points))

    samples = [-3.5 + i * .1 for i in range(91)]

    def density(model):
        return path([(x(v), y(model.pdf(v))) for v in samples])

    def area(model):
        values = [criterion] + [v for v in samples if v > criterion]
        return path([(x(criterion), 164)] + [(x(v), y(model.pdf(v))) for v in values]
                    + [(x(samples[-1]), 164)]) + ' Z'

    def roc(d):
        model = NormalDist(d, 1)
        rates = [(0, 0)] + [(1 - noise.cdf(c), 1 - model.cdf(c))
                           for c in [6 - i * .1 for i in range(101)]] + [(1, 1)]
        return path([(48 + a * 290, 218 - b * 190) for a, b in rates])

    def point(c):
        return {'x': round(48 + (1 - noise.cdf(c)) * 290, 3),
                'y': round(218 - (1 - signal.cdf(c)) * 190, 3)}

    return dict(phase=phase, d_prime=d_prime, criterion=criterion,
                noise_path=density(noise), signal_path=density(signal),
                noise_area=area(noise), signal_area=area(signal),
                criterion_x=round(x(criterion), 3), roc_path=roc(d_prime),
                previous_signal_path=density(NormalDist(1.5, 1)) if phase == 5 else None,
                previous_roc_path=roc(1.5) if phase == 5 else None,
                previous_point={'x': round(48 + false_alarm * 290, 3),
                                'y': round(218 - (1 - NormalDist(1.5, 1).cdf(criterion)) * 190, 3)} if phase == 5 else None,
                roc_points=[point(.75), point(criterion)],
                rates={'hit': hit, 'miss': 1 - hit,
                       'false_alarm': false_alarm, 'correct_rejection': 1 - false_alarm})
