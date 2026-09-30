import React from 'react';

interface UsageGuideModalProps {
  open: boolean;
  onClose: () => void;
}

const GUIDE_ROWS = [
  {
    feature: 'Nạp tệp đo',
    usage: 'Kéo thả hoặc chọn nhiều tệp .SOR, .MSOR hoặc .TRC tại vùng tải tệp.',
    note: 'Mỗi lần nạp mới sẽ thay toàn bộ lô trước. Nếu trộn định dạng, hệ thống chỉ nhận một loại theo thứ tự SOR → MSOR → TRC.',
  },
  {
    feature: 'Cấu hình thông số',
    usage: 'Chọn cấu hình mẫu hoặc nhập các ngưỡng, chiều dài tuyến, dung sai, kiểu đầu ra và thông số core.',
    note: 'Có thể xuất mẫu FastReporter hoặc STV. Thông số nâng cao bổ sung phạm vi và cách xử lý sheet Sections.',
  },
  {
    feature: 'Xuất báo cáo Excel',
    usage: 'Nhấn “Xuất báo cáo Excel”, nhập tên người xuất, đơn vị và tên tuyến rồi xác nhận.',
    note: 'Báo cáo được tải tự động sau khi xử lý. Nếu trình duyệt chặn tải, dùng nút “Tải báo cáo”.',
  },
  {
    feature: 'Đồ thị tuyến',
    usage: 'Mở “Đồ thị tuyến” để xem trace, bảng sự kiện và thông tin chi tiết của tệp đang chọn.',
    note: 'Dùng chung lô tệp với màn hình xuất Excel; hỗ trợ chọn trace, thu phóng, khôi phục và xuất PDF đồ thị.',
  },
  {
    feature: 'Lịch sử xuất file',
    usage: 'Mở mục lịch sử để xem thời gian xuất, người xuất, đơn vị và tên tuyến.',
    note: 'Danh sách được đọc từ kho lịch sử đã cấu hình cho hệ thống.',
  },
  {
    feature: 'Biểu đồ',
    usage: 'Chọn khu vực B-N, TBB hoặc DBB, sau đó chọn tuyến cần theo dõi.',
    note: 'Hiển thị dữ liệu 6 tháng gần nhất, gồm điểm lỗi nặng theo tháng và đánh giá tuyến theo QĐ 4.8.',
  },
  {
    feature: 'Thông báo',
    usage: 'Mở biểu tượng chuông để xem các thông báo xuất tuyến chưa đọc.',
    note: 'Bấm từng thông báo để đánh dấu đã đọc hoặc dùng “Đọc tất cả”; thông báo đã đọc sẽ biến mất và không còn được tính.',
  },
];

const UsageGuideModal: React.FC<UsageGuideModalProps> = ({ open, onClose }) => {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="usage-guide-title"
    >
      <div className="flex max-h-[88vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-outline-variant bg-white shadow-2xl animate-fade-up">
        <header className="flex shrink-0 items-center justify-between gap-4 border-b border-outline-variant px-5 py-4 md:px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <span className="material-symbols-outlined" aria-hidden="true">menu_book</span>
            </div>
            <div>
              <h2 id="usage-guide-title" className="font-headline-md text-xl font-bold text-industrial-navy">Hướng dẫn sử dụng</h2>
              <p className="text-xs text-on-surface-variant">Các bước và chức năng chính của PMB - TraceViewer</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-10 w-10 items-center justify-center rounded-full text-on-surface-variant transition-colors hover:bg-surface-variant hover:text-error"
            aria-label="Đóng hướng dẫn sử dụng"
          >
            <span className="material-symbols-outlined" aria-hidden="true">close</span>
          </button>
        </header>

        <div className="overflow-y-auto p-5 md:p-6">
          <section aria-labelledby="quick-guide-heading">
            <h3 id="quick-guide-heading" className="mb-3 text-sm font-bold uppercase tracking-wider text-industrial-navy">Quy trình xuất báo cáo nhanh</h3>
            <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {[
                ['01', 'Nạp tệp đo'],
                ['02', 'Chọn cấu hình'],
                ['03', 'Nhập thông tin tuyến'],
                ['04', 'Xuất và tải báo cáo'],
              ].map(([step, label]) => (
                <li key={step} className="flex items-center gap-3 rounded-xl border border-outline-variant bg-surface-container-lowest p-3">
                  <span className="font-mono-data text-lg font-bold text-primary">{step}</span>
                  <span className="text-sm font-semibold text-on-surface">{label}</span>
                </li>
              ))}
            </ol>
          </section>

          <section className="mt-6" aria-labelledby="feature-guide-heading">
            <h3 id="feature-guide-heading" className="mb-3 text-sm font-bold uppercase tracking-wider text-industrial-navy">Chi tiết chức năng</h3>
            <div className="overflow-x-auto rounded-xl border border-outline-variant">
              <table className="w-full min-w-[760px] border-collapse text-left">
                <thead className="bg-surface-container text-xs font-bold uppercase tracking-wider text-industrial-navy">
                  <tr>
                    <th className="w-[20%] border-b border-outline-variant p-4">Chức năng</th>
                    <th className="w-[38%] border-b border-outline-variant p-4">Cách sử dụng</th>
                    <th className="border-b border-outline-variant p-4">Kết quả và lưu ý</th>
                  </tr>
                </thead>
                <tbody className="text-sm text-on-surface">
                  {GUIDE_ROWS.map((row) => (
                    <tr key={row.feature} className="align-top even:bg-surface-container-lowest/70">
                      <th scope="row" className="border-b border-outline-variant p-4 font-bold text-industrial-navy">{row.feature}</th>
                      <td className="border-b border-outline-variant p-4 leading-relaxed">{row.usage}</td>
                      <td className="border-b border-outline-variant p-4 leading-relaxed text-on-surface-variant">{row.note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};

export default UsageGuideModal;
