import React, { useEffect, useMemo, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import {
  buildLossChartOption,
  buildQdChartOption,
  type DashboardRegion,
  type DashboardRoute,
  type DashboardSeries,
} from './dashboardSeries';


interface RouteDashboardModalProps {
  open: boolean;
  onClose: () => void;
}

const REGIONS: DashboardRegion[] = ['B-N', 'TBB', 'DBB'];

async function readJson(response: Response): Promise<any> {
  const payload = await response.json();
  if (!response.ok || payload?.status !== 'success') {
    throw new Error(payload?.detail || `Dashboard API returned ${response.status}`);
  }
  return payload.data;
}

const RouteDashboardModal: React.FC<RouteDashboardModalProps> = ({ open, onClose }) => {
  const [region, setRegion] = useState<DashboardRegion>('B-N');
  const [routes, setRoutes] = useState<DashboardRoute[]>([]);
  const [routeKey, setRouteKey] = useState('');
  const [series, setSeries] = useState<DashboardSeries | null>(null);
  const [loadingRoutes, setLoadingRoutes] = useState(false);
  const [loadingSeries, setLoadingSeries] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    if (!open) return undefined;
    const controller = new AbortController();
    setLoadingRoutes(true);
    setError(null);
    setRoutes([]);
    setRouteKey('');
    setSeries(null);
    fetch(`/trace/api/dashboard/routes?region=${encodeURIComponent(region)}`, {
      signal: controller.signal,
    })
      .then(readJson)
      .then((data) => {
        if (!Array.isArray(data)) throw new Error('Dashboard route list is invalid');
        setRoutes(data);
        setRouteKey(data[0]?.route_key || '');
      })
      .catch((fetchError) => {
        if (fetchError instanceof Error && fetchError.name === 'AbortError') return;
        console.error('Failed to load dashboard routes', fetchError);
        setError('Không thể tải danh sách tuyến. Vui lòng thử lại.');
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingRoutes(false);
      });
    return () => controller.abort();
  }, [open, region, refreshToken]);

  useEffect(() => {
    if (!open || !routeKey) return undefined;
    const controller = new AbortController();
    setLoadingSeries(true);
    setError(null);
    const params = new URLSearchParams({ region, route_key: routeKey, months: '6' });
    fetch(`/trace/api/dashboard/route?${params.toString()}`, { signal: controller.signal })
      .then(readJson)
      .then((data) => {
        if (!data || !Array.isArray(data.months)) {
          throw new Error('Dashboard series is invalid');
        }
        setSeries(data);
      })
      .catch((fetchError) => {
        if (fetchError instanceof Error && fetchError.name === 'AbortError') return;
        console.error('Failed to load dashboard series', fetchError);
        setSeries(null);
        setError('Không thể tải dữ liệu tuyến. Vui lòng thử lại.');
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingSeries(false);
      });
    return () => controller.abort();
  }, [open, region, routeKey, refreshToken]);

  const lossOption = useMemo(
    () => series ? buildLossChartOption(series) : null,
    [series],
  );
  const qdOption = useMemo(
    () => series ? buildQdChartOption(series) : null,
    [series],
  );

  if (!open) return null;

  const periodEnd = series?.period_end
    ? new Date(`${series.period_end}T00:00:00`).toLocaleDateString('vi-VN', { month: '2-digit', year: 'numeric' })
    : '';

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-[100] flex items-center justify-center">
      <section
        className="bg-surface rounded-2xl shadow-2xl p-5 sm:p-6 w-[97%] max-w-6xl max-h-[92vh] overflow-y-auto border border-outline-variant animate-fade-up"
        aria-labelledby="route-dashboard-title"
        aria-busy={loadingRoutes || loadingSeries}
      >
        <header className="flex justify-between items-start gap-4 mb-5">
          <div>
            <h2 id="route-dashboard-title" className="text-xl font-headline-md font-bold text-industrial-navy flex items-center gap-2">
              <span className="material-symbols-outlined" aria-hidden="true">monitoring</span>
              Biểu đồ
            </h2>
            <p className="mt-1 text-xs text-on-surface-variant">
              Dữ liệu đo và bảng đánh giá theo QĐ 4.8 trong 6 tháng dữ liệu gần nhất.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setRefreshToken((value) => value + 1)}
              disabled={loadingRoutes || loadingSeries}
              className="h-9 px-3 rounded-lg border border-outline-variant bg-white text-xs font-bold text-industrial-navy hover:bg-surface-container disabled:opacity-50 transition-colors flex items-center gap-1.5"
            >
              <span className="material-symbols-outlined text-[17px]" aria-hidden="true">refresh</span>
              Làm mới
            </button>
            <button
              type="button"
              onClick={onClose}
              className="h-9 w-9 rounded-lg text-on-surface-variant hover:text-error hover:bg-error-container/40 transition-colors flex items-center justify-center"
              aria-label="Đóng biểu đồ"
            >
              <span className="material-symbols-outlined" aria-hidden="true">close</span>
            </button>
          </div>
        </header>

        <div className="rounded-xl border border-outline-variant bg-white p-4 mb-4">
          <div className="flex flex-wrap gap-2" aria-label="Chọn khu vực">
            {REGIONS.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setRegion(item)}
                aria-pressed={region === item}
                className={region === item
                  ? 'min-w-20 px-4 py-2 rounded-lg bg-primary text-white text-sm font-bold shadow-sm'
                  : 'min-w-20 px-4 py-2 rounded-lg border border-outline-variant text-on-surface-variant text-sm font-bold hover:bg-surface-container'}
              >
                {item}
              </button>
            ))}
          </div>
          <div className="mt-4 grid grid-cols-1 md:grid-cols-[140px_minmax(0,420px)] items-center gap-2">
            <label htmlFor="dashboard-route" className="text-sm font-bold text-industrial-navy">Chọn tuyến:</label>
            <select
              id="dashboard-route"
              value={routeKey}
              onChange={(event) => setRouteKey(event.target.value)}
              disabled={loadingRoutes || routes.length === 0}
              className="w-full rounded-lg border border-outline-variant bg-white px-3 py-2.5 text-sm text-on-surface outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 disabled:opacity-60"
            >
              {routes.length === 0 && <option value="">Không có tuyến</option>}
              {routes.map((route) => (
                <option key={route.route_key} value={route.route_key}>{route.route_name}</option>
              ))}
            </select>
          </div>
        </div>

        {error ? (
          <div className="min-h-48 rounded-xl border border-error/30 bg-error-container/40 flex flex-col items-center justify-center gap-3 text-center p-6">
            <span className="material-symbols-outlined text-[36px] text-error" aria-hidden="true">cloud_off</span>
            <p className="font-bold text-error">{error}</p>
            <p className="text-xs text-on-surface-variant">Hệ thống không hiển thị số liệu ước đoán khi nguồn dữ liệu chưa sẵn sàng.</p>
          </div>
        ) : loadingRoutes || loadingSeries ? (
          <div className="min-h-64 rounded-xl border border-outline-variant bg-white flex flex-col items-center justify-center gap-3 text-on-surface-variant">
            <span className="material-symbols-outlined text-[32px] animate-spin" aria-hidden="true">progress_activity</span>
            <span className="text-sm font-medium">Đang tải dữ liệu tuyến...</span>
          </div>
        ) : series && lossOption && qdOption ? (
          <div className="space-y-4">
            <div className="rounded-xl border border-primary/15 bg-primary-fixed/30 px-4 py-3 flex flex-wrap gap-x-6 gap-y-1 text-sm">
              <strong className="text-industrial-navy">Tuyến: {series.route_name}</strong>
              <span>Khu vực: <strong>{series.region}</strong></span>
              <span>Thời gian: <strong>6 tháng gần nhất đến {periodEnd}</strong></span>
            </div>
            <article className="rounded-xl border border-outline-variant bg-white p-4">
              <h3 className="text-base font-bold text-industrial-navy">Điểm lỗi nặng theo tháng</h3>
              <p className="mt-1 text-xs text-on-surface-variant">Mỗi tháng lấy điểm có mức suy hao lớn nhất; tháng thiếu dữ liệu được để trống.</p>
              <div role="img" aria-label="Biểu đồ điểm lỗi nặng theo tháng">
                <ReactECharts option={lossOption} style={{ height: 320 }} notMerge lazyUpdate />
              </div>
            </article>
            <article className="rounded-xl border border-outline-variant bg-white p-4">
              <h3 className="text-base font-bold text-industrial-navy">Đánh giá tuyến theo QĐ 4.8</h3>
              <p className="mt-1 text-xs text-on-surface-variant">So sánh DKD Core với ngưỡng yêu cầu 70%, 80% hoặc 85% ghi trong workbook.</p>
              <div role="img" aria-label="Biểu đồ đánh giá tuyến theo QĐ 4.8">
                <ReactECharts option={qdOption} style={{ height: 320 }} notMerge lazyUpdate />
              </div>
            </article>
          </div>
        ) : (
          <div className="min-h-48 rounded-xl border border-outline-variant bg-white flex items-center justify-center text-sm text-on-surface-variant">
            Khu vực chưa có dữ liệu tuyến.
          </div>
        )}
      </section>
    </div>
  );
};

export default RouteDashboardModal;
