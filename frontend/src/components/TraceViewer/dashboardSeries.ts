import type { EChartsOption } from 'echarts';

export type DashboardRegion = 'B-N' | 'TBB' | 'DBB';

export interface DashboardRoute {
  route_key: string;
  route_name: string;
}

export interface DashboardMonth {
  month: string;
  month_label: string;
  worst_event_loss_db: number | null;
  worst_event_position_km: number | null;
  utilization_percent: number | null;
  dkd_core_percent: number | null;
  dkd_required_percent: number | null;
  assessment: 'Đạt' | 'Không đạt' | null;
  loss_source: { file: string; sheet: string } | null;
  qd_source: { file: string; sheet: string } | null;
}

export interface DashboardSeries {
  region: DashboardRegion;
  route_key: string;
  route_name: string;
  period_start: string;
  period_end: string;
  months: DashboardMonth[];
}

const axisStyle = {
  axisLine: { lineStyle: { color: '#c5c5d7' } },
  axisLabel: { color: '#444654', fontSize: 11 },
};

export function buildLossChartOption(series: DashboardSeries): EChartsOption {
  return {
    animationDuration: 350,
    color: ['#001e81'],
    grid: { left: 58, right: 24, top: 30, bottom: 48 },
    tooltip: {
      trigger: 'axis',
      formatter: (items: any) => {
        const index = Array.isArray(items) && items.length ? items[0].dataIndex : -1;
        const month = series.months[index];
        if (!month || month.worst_event_loss_db === null) {
          return month ? `<strong>${month.month_label}</strong><br/>Không có dữ liệu điểm lỗi` : '';
        }
        return [
          `<strong>${month.month_label}</strong>`,
          `Vị trí: <strong>Km ${month.worst_event_position_km?.toLocaleString('vi-VN', { maximumFractionDigits: 3 })}</strong>`,
          `Suy hao: <strong>${month.worst_event_loss_db.toLocaleString('vi-VN', { maximumFractionDigits: 3 })} dB</strong>`,
        ].join('<br/>');
      },
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: series.months.map((month) => month.month_label),
      ...axisStyle,
    },
    yAxis: {
      type: 'value',
      name: 'dB',
      min: 0,
      nameTextStyle: { color: '#444654' },
      splitLine: { lineStyle: { color: '#eeedf8' } },
      ...axisStyle,
    },
    series: [{
      name: 'Điểm lỗi nặng nhất',
      type: 'line',
      connectNulls: false,
      symbol: 'circle',
      symbolSize: 9,
      lineStyle: { width: 3 },
      areaStyle: { color: 'rgba(0, 30, 129, 0.08)' },
      data: series.months.map((month) => month.worst_event_loss_db),
    }],
  };
}

export function buildQdChartOption(series: DashboardSeries): EChartsOption {
  return {
    animationDuration: 350,
    color: ['#001e81', '#f59e0b'],
    grid: { left: 58, right: 24, top: 52, bottom: 48 },
    legend: {
      top: 4,
      textStyle: { color: '#444654', fontSize: 11 },
      data: ['DKD Core', 'DKD yêu cầu'],
    },
    tooltip: {
      trigger: 'axis',
      formatter: (items: any) => {
        const index = Array.isArray(items) && items.length ? items[0].dataIndex : -1;
        const month = series.months[index];
        if (!month || month.dkd_core_percent === null) {
          return month ? `<strong>${month.month_label}</strong><br/>Không có bảng đánh giá QĐ 4.8` : '';
        }
        const rows = [
          `<strong>${month.month_label}</strong>`,
          `DKD Core: <strong>${month.dkd_core_percent.toLocaleString('vi-VN', { maximumFractionDigits: 2 })}%</strong>`,
        ];
        if (month.dkd_required_percent !== null) {
          rows.push(`DKD yêu cầu: <strong>${month.dkd_required_percent.toLocaleString('vi-VN', { maximumFractionDigits: 2 })}%</strong>`);
        }
        if (month.assessment) rows.push(`Đánh giá: <strong>${month.assessment}</strong>`);
        return rows.join('<br/>');
      },
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: series.months.map((month) => month.month_label),
      ...axisStyle,
    },
    yAxis: {
      type: 'value',
      name: '%',
      min: 0,
      max: 100,
      nameTextStyle: { color: '#444654' },
      splitLine: { lineStyle: { color: '#eeedf8' } },
      ...axisStyle,
    },
    series: [
      {
        name: 'DKD Core',
        type: 'line',
        connectNulls: false,
        symbol: 'circle',
        symbolSize: 10,
        lineStyle: { width: 3 },
        data: series.months.map((month) => ({
          value: month.dkd_core_percent,
          itemStyle: {
            color: month.assessment === 'Đạt'
              ? '#22c55e'
              : month.assessment === 'Không đạt'
                ? '#ef4444'
                : '#001e81',
          },
        })),
      },
      {
        name: 'DKD yêu cầu',
        type: 'line',
        connectNulls: false,
        symbol: 'none',
        lineStyle: { type: 'dashed', width: 2, color: '#f59e0b' },
        data: series.months.map((month) => month.dkd_required_percent),
      },
    ],
  };
}
