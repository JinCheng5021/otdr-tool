import React, { useState, useEffect } from 'react';

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
  const [historyData, setHistoryData] = useState<any[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Expose opening history modal to the window object so App.tsx can call it (a bit hacky but works for the current App structure)
  // Or better, since App.tsx has its own "Lịch sử" buttons, we can listen to a custom event.
  useEffect(() => {
    const handleOpenHistory = () => {
      setIsHistoryModalOpen(true);
      fetchHistory();
    };
    window.addEventListener('open-history-modal', handleOpenHistory);
    return () => window.removeEventListener('open-history-modal', handleOpenHistory);
  }, []);

  const fetchHistory = async () => {
    setHistoryLoading(true);
    try {
      const res = await fetch('/trace/api/history');
      if (res.ok) {
        const json = await res.json();
        setHistoryData(json.data || []);
      }
    } catch (e) {
      console.error('Failed to fetch history', e);
    } finally {
      setHistoryLoading(false);
    }
  };

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
    </>
  );
};

export default Modals;
