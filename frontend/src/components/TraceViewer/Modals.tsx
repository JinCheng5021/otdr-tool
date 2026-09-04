import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  summarizeExportHistory,
  type ExportHistoryRecord,
} from './historyStats';

interface ModalsProps {
  isExportModalOpen: boolean;
  setIsExportModalOpen: (open: boolean) => void;
  onConfirmExport: (data: { exporterName: string; exporterUnit: string; exportRoute: string }) => void;
}

const Modals: React.FC<ModalsProps> = ({ isExportModalOpen, setIsExportModalOpen, onConfirmExport }) => {
  const [exporterName, setExporterName] = useState('');
  const [exporterUnit, setExporterUnit] = useState('');
  const [exportRoute, setExportRoute] = useState('');

  const [isHistoryModalOpen, setIsHistoryModalOpen] = useState(false);
  const [isStatusChartModalOpen, setIsStatusChartModalOpen] = useState(false);
  const [historyData, setHistoryData] = useState<ExportHistoryRecord[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const historySummary = useMemo(
    () => summarizeExportHistory(historyData),
    [historyData],
  );

  const fetchHistory = useCallback(async () => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const res = await fetch('/trace/api/history');
      if (!res.ok) {
        throw new Error(`History API returned ${res.status}`);
      }
      const json = await res.json();
      if (!Array.isArray(json.data)) {
        throw new Error('History API returned invalid data');
      }
      setHistoryData(json.data);
    } catch (error) {
      setHistoryData([]);
      setHistoryError('Không thể tải dữ liệu lịch sử. Vui lòng thử lại.');
      console.error('Failed to fetch history', error);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  // Expose opening history modal to the window object so App.tsx can call it (a bit hacky but works for the current App structure)
  // Or better, since App.tsx has its own "Lịch sử" buttons, we can listen to a custom event.
  useEffect(() => {
    const handleOpenHistory = () => {
      setIsHistoryModalOpen(true);
      void fetchHistory();
    };
    const handleOpenStatusChart = () => {
      setIsStatusChartModalOpen(true);
      void fetchHistory();
    };
    window.addEventListener('open-history-modal', handleOpenHistory);
    window.addEventListener('open-status-chart-modal', handleOpenStatusChart);
    return () => {
      window.removeEventListener('open-history-modal', handleOpenHistory);
      window.removeEventListener('open-status-chart-modal', handleOpenStatusChart);
    };
  }, [fetchHistory]);

  const handleConfirm = () => {
    if (!exporterName || !exporterUnit || !exportRoute) {
      alert('Vui lòng điền đầy đủ thông tin bắt buộc (*)');
      return;
    }
    onConfirmExport({ exporterName, exporterUnit, exportRoute });
  };

  return (
    <>
      {/* Export Modal */}
      {isExportModalOpen && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-[100] flex items-center justify-center">
          <div className="bg-white rounded-2xl shadow-2xl p-6 w-[90%] max-w-md border border-outline-variant animate-fade-up">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-headline-md font-bold text-industrial-navy">Thông tin xuất file</h2>
              <button onClick={() => setIsExportModalOpen(false)} className="text-on-surface-variant hover:text-error transition-colors">
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            <div className="space-y-4">
              <div className="space-y-1">
                <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Tên người xuất <span className="text-error">*</span></label>
                <input value={exporterName} onChange={(e) => setExporterName(e.target.value)} type="text" className="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" placeholder="Ví dụ: Nguyễn Văn A" />
              </div>
              <div className="space-y-1">
                <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Đơn vị <span className="text-error">*</span></label>
                <input value={exporterUnit} onChange={(e) => setExporterUnit(e.target.value)} type="text" className="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" placeholder="Ví dụ: INF MN" />
              </div>
              <div className="space-y-1">
                <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Tuyến xuất <span className="text-error">*</span></label>
                <input value={exportRoute} onChange={(e) => setExportRoute(e.target.value)} type="text" className="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" placeholder="Ví dụ: Tuyến số 1" />
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <button onClick={() => setIsExportModalOpen(false)} className="px-5 py-2.5 rounded-lg text-on-surface-variant font-bold hover:bg-surface-variant transition-colors">Hủy</button>
              <button onClick={handleConfirm} className="px-5 py-2.5 rounded-lg bg-primary text-white font-bold hover:bg-industrial-navy transition-colors flex items-center gap-2 shadow-lg shadow-primary/20">
                <span className="material-symbols-outlined text-[18px]">check_circle</span> Xác nhận
              </button>
            </div>
          </div>
        </div>
      )}

      {/* History Modal */}
      {isHistoryModalOpen && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-[100] flex items-center justify-center">
          <div className="bg-white rounded-2xl shadow-2xl p-6 w-[95%] max-w-4xl max-h-[85vh] border border-outline-variant flex flex-col animate-fade-up">
            <div className="flex justify-between items-center mb-4 shrink-0">
              <h2 className="text-xl font-headline-md font-bold text-industrial-navy flex items-center gap-2">
                <span className="material-symbols-outlined">history</span> Lịch sử xuất báo cáo
              </h2>
              <button onClick={() => setIsHistoryModalOpen(false)} className="text-on-surface-variant hover:text-error transition-colors">
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            <div className="overflow-auto rounded-xl border border-outline-variant">
              <table className="w-full text-left border-collapse">
                <thead className="bg-surface-container text-[12px] uppercase font-bold text-industrial-navy sticky top-0">
                  <tr>
                    <th className="p-4 border-b border-outline-variant">Thời gian</th>
                    <th className="p-4 border-b border-outline-variant">Người xuất</th>
                    <th className="p-4 border-b border-outline-variant">Đơn vị</th>
                    <th className="p-4 border-b border-outline-variant">Tuyến</th>
                  </tr>
                </thead>
                <tbody className="text-sm font-medium text-on-surface">
                  {historyLoading ? (
                    <tr><td colSpan={4} className="p-6 text-center text-on-surface-variant">Đang tải dữ liệu...</td></tr>
                  ) : historyError ? (
                    <tr><td colSpan={4} className="p-6 text-center text-error">{historyError}</td></tr>
                  ) : historyData.length === 0 ? (
                    <tr><td colSpan={4} className="p-6 text-center text-on-surface-variant">Không có lịch sử nào.</td></tr>
                  ) : (
                    historyData.map((row, idx) => (
                      <tr key={idx} className="hover:bg-surface-container/50">
                        <td className="p-4 border-b border-outline-variant">{row.export_time}</td>
                        <td className="p-4 border-b border-outline-variant">{row.exporter_name}</td>
                        <td className="p-4 border-b border-outline-variant">{row.unit}</td>
                        <td className="p-4 border-b border-outline-variant">{row.route_name}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Export status chart modal */}
      {isStatusChartModalOpen && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-[100] flex items-center justify-center">
          <section
            className="bg-surface rounded-2xl shadow-2xl p-6 w-[95%] max-w-4xl max-h-[85vh] overflow-y-auto border border-outline-variant animate-fade-up"
            aria-labelledby="status-chart-title"
            aria-busy={historyLoading}
          >
            <div className="flex justify-between items-start gap-4 mb-5">
              <div>
                <h2
                  id="status-chart-title"
                  className="text-xl font-headline-md font-bold text-industrial-navy flex items-center gap-2"
                >
                  <span className="material-symbols-outlined" aria-hidden="true">monitoring</span>
                  Biểu đồ
                </h2>
                <p className="mt-1 text-xs text-on-surface-variant">
                  Thống kê từ dữ liệu lịch sử xuất file đã được hệ thống ghi nhận.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => void fetchHistory()}
                  disabled={historyLoading}
                  className="h-9 px-3 rounded-lg border border-outline-variant bg-white text-xs font-bold text-industrial-navy hover:bg-surface-container disabled:opacity-50 transition-colors flex items-center gap-1.5"
                  aria-label="Làm mới biểu đồ"
                >
                  <span className="material-symbols-outlined text-[17px]" aria-hidden="true">refresh</span>
                  Làm mới
                </button>
                <button
                  type="button"
                  onClick={() => setIsStatusChartModalOpen(false)}
                  className="h-9 w-9 rounded-lg text-on-surface-variant hover:text-error hover:bg-error-container/40 transition-colors flex items-center justify-center"
                  aria-label="Đóng biểu đồ"
                >
                  <span className="material-symbols-outlined" aria-hidden="true">close</span>
                </button>
              </div>
            </div>

            {historyLoading ? (
              <div className="min-h-[300px] rounded-xl border border-outline-variant bg-white flex flex-col items-center justify-center gap-3 text-on-surface-variant">
                <span className="material-symbols-outlined text-[32px] animate-spin" aria-hidden="true">progress_activity</span>
                <span className="text-sm font-medium">Đang tải dữ liệu thống kê...</span>
              </div>
            ) : historyError ? (
              <div className="min-h-[260px] rounded-xl border border-error/30 bg-error-container/40 flex flex-col items-center justify-center gap-3 text-center p-6">
                <span className="material-symbols-outlined text-[36px] text-error" aria-hidden="true">cloud_off</span>
                <p className="font-bold text-error">{historyError}</p>
                <p className="text-xs text-on-surface-variant">Biểu đồ không hiển thị số liệu ước đoán khi nguồn dữ liệu chưa sẵn sàng.</p>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <article className="rounded-xl border border-outline-variant bg-white p-4">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-[11px] font-bold uppercase tracking-wider text-on-surface-variant">Bản ghi đã tải</span>
                      <span className="material-symbols-outlined text-[20px] text-primary" aria-hidden="true">description</span>
                    </div>
                    <strong
                      className="block mt-2 font-mono-data text-3xl text-industrial-navy"
                      aria-label="Số bản ghi đã tải"
                    >
                      {historySummary.loadedRecords.toLocaleString('vi-VN')}
                    </strong>
                  </article>
                  <article className="rounded-xl border border-outline-variant bg-white p-4">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-[11px] font-bold uppercase tracking-wider text-on-surface-variant">Xuất hôm nay</span>
                      <span className="material-symbols-outlined text-[20px] text-status-pass" aria-hidden="true">task_alt</span>
                    </div>
                    <strong
                      className="block mt-2 font-mono-data text-3xl text-status-pass"
                      aria-label="Số lượt xuất hôm nay"
                    >
                      {historySummary.exportsToday.toLocaleString('vi-VN')}
                    </strong>
                  </article>
                  <article className="rounded-xl border border-outline-variant bg-white p-4">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-[11px] font-bold uppercase tracking-wider text-on-surface-variant">Tuyến ghi nhận</span>
                      <span className="material-symbols-outlined text-[20px] text-primary" aria-hidden="true">route</span>
                    </div>
                    <strong
                      className="block mt-2 font-mono-data text-3xl text-industrial-navy"
                      aria-label="Số tuyến ghi nhận"
                    >
                      {historySummary.uniqueRoutes.toLocaleString('vi-VN')}
                    </strong>
                  </article>
                </div>

                <article className="rounded-xl border border-outline-variant bg-white p-4 sm:p-5">
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-5">
                    <div>
                      <h3 className="text-sm font-bold text-industrial-navy">Lượt xuất trong 7 ngày gần nhất</h3>
                      <p className="text-[11px] text-on-surface-variant mt-0.5">Mỗi cột là số bản ghi xuất file theo ngày.</p>
                    </div>
                    <span className="self-start sm:self-auto inline-flex items-center gap-1.5 rounded-full border border-status-pass/20 bg-status-pass/10 px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-status-pass">
                      <span className="w-1.5 h-1.5 rounded-full bg-status-pass" aria-hidden="true"></span>
                      Dữ liệu sẵn sàng
                    </span>
                  </div>

                  <div
                    className="grid grid-cols-7 gap-2 h-48"
                    role="img"
                    aria-label={`Biểu đồ lượt xuất 7 ngày gần nhất: ${historySummary.dailyExports
                      .map((day) => `${day.label} có ${day.count} lượt`)
                      .join(', ')}`}
                  >
                    {historySummary.dailyExports.map((day) => {
                      const height = historySummary.maximumDailyCount === 0
                        ? 0
                        : (day.count / historySummary.maximumDailyCount) * 100;
                      return (
                        <div key={day.dateKey} className="min-w-0 flex flex-col items-center">
                          <span className="h-6 text-[11px] font-mono-data font-bold text-industrial-navy">
                            {day.count}
                          </span>
                          <div className="w-full flex-1 rounded-t-lg bg-surface-container-low flex items-end justify-center overflow-hidden">
                            <div
                              className="w-full max-w-10 rounded-t-md bg-primary transition-[height] duration-500"
                              style={{ height: day.count > 0 ? `${Math.max(10, height)}%` : '0%' }}
                              aria-hidden="true"
                            ></div>
                          </div>
                          <span className="mt-2 text-[10px] sm:text-[11px] font-semibold text-on-surface-variant">
                            {day.label}
                          </span>
                        </div>
                      );
                    })}
                  </div>

                  {historySummary.loadedRecords === 0 && (
                    <p className="mt-4 text-center text-xs text-on-surface-variant">
                      Chưa có bản ghi xuất file để hiển thị trên biểu đồ.
                    </p>
                  )}
                </article>

                <p className="text-[11px] text-on-surface-variant">
                  Lưu ý: số liệu được tính trên tối đa 100 bản ghi gần nhất do API lịch sử trả về.
                </p>
              </div>
            )}
          </section>
        </div>
      )}
    </>
  );
};

export default Modals;
