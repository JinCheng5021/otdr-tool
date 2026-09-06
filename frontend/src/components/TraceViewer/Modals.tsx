import React, { useCallback, useEffect, useState } from 'react';
import type { ExportHistoryRecord } from './historyStats';
import RouteDashboardModal from './RouteDashboardModal';

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

  const fetchHistory = useCallback(async () => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const response = await fetch('/trace/api/history');
      if (!response.ok) throw new Error(`History API returned ${response.status}`);
      const payload = await response.json();
      if (!Array.isArray(payload.data)) throw new Error('History API returned invalid data');
      setHistoryData(payload.data);
    } catch (error) {
      setHistoryData([]);
      setHistoryError('Không thể tải dữ liệu lịch sử. Vui lòng thử lại.');
      console.error('Failed to fetch history', error);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    const handleOpenHistory = () => {
      setIsHistoryModalOpen(true);
      void fetchHistory();
    };
    const handleOpenStatusChart = () => setIsStatusChartModalOpen(true);
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
      {isExportModalOpen && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-[100] flex items-center justify-center">
          <div className="bg-white rounded-2xl shadow-2xl p-6 w-[90%] max-w-md border border-outline-variant animate-fade-up">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-headline-md font-bold text-industrial-navy">Thông tin xuất file</h2>
              <button type="button" onClick={() => setIsExportModalOpen(false)} className="text-on-surface-variant hover:text-error transition-colors" aria-label="Đóng thông tin xuất file">
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            <div className="space-y-4">
              <div className="space-y-1">
                <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Tên người xuất <span className="text-error">*</span></label>
                <input value={exporterName} onChange={(event) => setExporterName(event.target.value)} type="text" className="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" placeholder="Ví dụ: Nguyễn Văn A" />
              </div>
              <div className="space-y-1">
                <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Đơn vị <span className="text-error">*</span></label>
                <input value={exporterUnit} onChange={(event) => setExporterUnit(event.target.value)} type="text" className="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" placeholder="Ví dụ: INF MN" />
              </div>
              <div className="space-y-1">
                <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Tuyến xuất <span className="text-error">*</span></label>
                <input value={exportRoute} onChange={(event) => setExportRoute(event.target.value)} type="text" className="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" placeholder="Ví dụ: Tuyến số 1" />
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <button type="button" onClick={() => setIsExportModalOpen(false)} className="px-5 py-2.5 rounded-lg text-on-surface-variant font-bold hover:bg-surface-variant transition-colors">Hủy</button>
              <button type="button" onClick={handleConfirm} className="px-5 py-2.5 rounded-lg bg-primary text-white font-bold hover:bg-industrial-navy transition-colors flex items-center gap-2 shadow-lg shadow-primary/20">
                <span className="material-symbols-outlined text-[18px]">check_circle</span> Xác nhận
              </button>
            </div>
          </div>
        </div>
      )}

      {isHistoryModalOpen && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-[100] flex items-center justify-center">
          <div className="bg-white rounded-2xl shadow-2xl p-6 w-[95%] max-w-4xl max-h-[85vh] border border-outline-variant flex flex-col animate-fade-up">
            <div className="flex justify-between items-center mb-4 shrink-0">
              <h2 className="text-xl font-headline-md font-bold text-industrial-navy flex items-center gap-2"><span className="material-symbols-outlined">history</span> Lịch sử xuất báo cáo</h2>
              <button type="button" onClick={() => setIsHistoryModalOpen(false)} className="text-on-surface-variant hover:text-error transition-colors" aria-label="Đóng lịch sử xuất báo cáo"><span className="material-symbols-outlined">close</span></button>
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
                  ) : historyData.map((row) => (
                    <tr key={row.id} className="hover:bg-surface-container/50">
                      <td className="p-4 border-b border-outline-variant">{row.export_time}</td>
                      <td className="p-4 border-b border-outline-variant">{row.exporter_name}</td>
                      <td className="p-4 border-b border-outline-variant">{row.unit}</td>
                      <td className="p-4 border-b border-outline-variant">{row.route_name}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      <RouteDashboardModal open={isStatusChartModalOpen} onClose={() => setIsStatusChartModalOpen(false)} />
    </>
  );
};

export default Modals;
