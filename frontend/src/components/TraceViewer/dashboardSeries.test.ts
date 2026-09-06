import {
  buildLossChartOption,
  buildQdChartOption,
  type DashboardSeries,
} from './dashboardSeries';


const series: DashboardSeries = {
  region: 'DBB',
  route_key: 'cpa--tyn',
  route_name: 'TYN - CPA',
  period_start: '2026-02-01',
  period_end: '2026-07-01',
  months: [
    {
      month: '2026-02', month_label: 'Tháng 2', worst_event_loss_db: null,
      worst_event_position_km: null, utilization_percent: null,
      dkd_core_percent: null, dkd_required_percent: null, assessment: null,
      loss_source: null, qd_source: null,
    },
    {
      month: '2026-03', month_label: 'Tháng 3', worst_event_loss_db: 18.779,
      worst_event_position_km: 2.542644, utilization_percent: 50,
      dkd_core_percent: 50, dkd_required_percent: 80, assessment: 'Không đạt',
      loss_source: { file: 'DBB T3.xlsx', sheet: 'CPA - TYN' },
      qd_source: { file: 'DBB T3.xlsx', sheet: 'CPA - TYN' },
    },
  ],
};

test('loss chart preserves a missing month instead of inventing zero', () => {
  const option: any = buildLossChartOption(series);
  expect(option.series[0].data).toEqual([null, 18.779]);
  expect(option.series[0].connectNulls).toBe(false);
});

test('QĐ 4.8 chart uses the dynamic requirement stored in Excel', () => {
  const option: any = buildQdChartOption(series);
  expect(option.series[0].data.map((point: any) => point.value)).toEqual([null, 50]);
  expect(option.series[1].data).toEqual([null, 80]);
  expect(option.series[0].data[1].itemStyle.color).toBe('#ef4444');
});
