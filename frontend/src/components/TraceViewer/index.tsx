import React, { useEffect, useState, useRef } from 'react';
import Modals from './Modals';
import {
  type StorageConversionResult,
  type InputFileSelection,
  downloadFromSignedUrl,
  parseStorageConversionResponse,
  requestStorageInput,
  requestSignedDownload,
  selectInputFiles,
  uploadFilesToStorage,
} from './traceExport';

const REPORT_PROCESSING_TIMEOUT_MS = 180 * 1000;

interface TraceViewerProps {
  files: File[];
  replaceInputFiles: (files: File[]) => InputFileSelection;
  clearInputFiles: () => void;
  parameterMode: 'basic' | 'advanced';
  onParameterModeChange: (mode: 'basic' | 'advanced') => void;
}

const TraceViewer: React.FC<TraceViewerProps> = ({
  files,
  replaceInputFiles,
  clearInputFiles,
  parameterMode,
  onParameterModeChange,
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Status message
  const [status, setStatus] = useState<{ message: string; type: 'error' | 'success' | 'info' } | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [readyReport, setReadyReport] = useState<StorageConversionResult | null>(null);
  const activeTab = parameterMode;

  // Modals state
  const [isExportModalOpen, setIsExportModalOpen] = useState(false);

  // Basic Parameters
  const [threshold, setThreshold] = useState('0.10');
  const [sectionThreshold, setSectionThreshold] = useState('');
  const [durationThreshold, setDurationThreshold] = useState('15');
  const [deviation, setDeviation] = useState('5');
  const [expectedLength, setExpectedLength] = useState('');
  const [routeTolerance, setRouteTolerance] = useState('0.300');
  const [outputMode, setOutputMode] = useState('fastreporter');
  const [stvTotalCore, setStvTotalCore] = useState('');
  const [stvUsedCore, setStvUsedCore] = useState('');

  // Advanced Parameters
  const [sectionExportScope, setSectionExportScope] = useState('all');
  const [segmentStart, setSegmentStart] = useState('');
  const [segmentEnd, setSegmentEnd] = useState('');
  const [sectionDetailLevel, setSectionDetailLevel] = useState('balanced');
  const [sectionMergeTolerance, setSectionMergeTolerance] = useState('100');
  const [sectionMinLength, setSectionMinLength] = useState('0');
  const [sectionEventSource, setSectionEventSource] = useState('all');
  const [sectionBoundaryPriority, setSectionBoundaryPriority] = useState('event');
  const [sectionAllowSplit, setSectionAllowSplit] = useState('false');
  const [sectionMatchTolerance, setSectionMatchTolerance] = useState('100');
  const [sectionMeasurementMode, setSectionMeasurementMode] = useState('fit');

  const resetSectionRange = () => {
    setSectionExportScope('all');
    setSegmentStart('');
    setSegmentEnd('');
  };

  useEffect(() => {
    if (parameterMode === 'basic') {
      setSectionExportScope('all');
      setSegmentStart('');
      setSegmentEnd('');
    }
  }, [parameterMode]);

  const applyPreset = (preset: string) => {
    switch (preset) {
      case 'compact':
        resetSectionRange();
        setSectionDetailLevel('minimum');
        setDeviation('15');
        setSectionMergeTolerance('300');
        setSectionAllowSplit('false');
        break;
      case 'daily':
        resetSectionRange();
        setSectionDetailLevel('balanced');
        setDeviation('5');
        setSectionMergeTolerance('100');
        setSectionAllowSplit('false');
        break;
      case 'detailed':
        resetSectionRange();
        setSectionDetailLevel('maximum');
        setDeviation('2');
        setSectionMergeTolerance('20');
        setSectionAllowSplit('true');
        break;
      case 'range':
        setSectionExportScope('selected_range');
        onParameterModeChange('advanced');
        break;
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const addFiles = (incomingFiles: File[]) => {
    if (incomingFiles.length === 0) return;
    try {
      const selection = replaceInputFiles(incomingFiles);
      setReadyReport(null);
      setStatus({
        message: selection.ignoredFiles.length > 0
          ? `Đã chọn ${selection.selectedFiles.length} file ${selection.selectedExtension}; bỏ qua ${selection.ignoredFiles.length} file khác định dạng.`
          : `Đã chọn ${selection.selectedFiles.length} file ${selection.selectedExtension}.`,
        type: 'info',
      });
    } catch (error) {
      setStatus({
        message: error instanceof Error ? error.message : 'Danh sách file không hợp lệ.',
        type: 'error',
      });
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files) {
      addFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      addFiles(Array.from(e.target.files));
      e.target.value = '';
    }
  };

  const removeFile = (index: number) => {
    const remainingFiles = files.filter((_, i) => i !== index);
    if (remainingFiles.length > 0) {
      replaceInputFiles(remainingFiles);
    } else {
      clearInputFiles();
    }
    setReadyReport(null);
  };

  const clearFiles = () => {
    clearInputFiles();
    setReadyReport(null);
    setStatus(null);
  };

  const handleExportClick = () => {
    if (isProcessing) return;
    if (files.length === 0) {
      setStatus({ message: 'Vui lòng chọn ít nhất 1 file để xuất báo cáo.', type: 'error' });
      return;
    }
    setIsExportModalOpen(true);
  };

  const handleConfirmExport = async (exportData: { exporterName: string; exporterUnit: string; exportRoute: string }) => {
    setIsExportModalOpen(false);
    setIsProcessing(true);
    setReadyReport(null);
    setStatus({ message: 'Đang khởi tạo phiên tải tệp...', type: 'info' });

    try {
      const selection = selectInputFiles(files);
      const selectedFiles = selection.selectedFiles;
      const session = await requestStorageInput(selectedFiles);
      setStatus({ message: 'Đang tải dữ liệu lên... 0%', type: 'info' });
      await uploadFilesToStorage(selectedFiles, session, (percentage) => setStatus({
        message: `Đang tải dữ liệu lên... ${percentage}%`,
        type: 'info',
      }));

      const formData = new FormData();
      formData.append('upload_id', session.upload_id);
      formData.append('input_manifest', JSON.stringify(session.files));

      formData.append('threshold_db', threshold);
      formData.append('section_threshold_db', sectionThreshold);
      formData.append('duration_threshold_s', durationThreshold);
      formData.append('deviation_m', deviation);
      formData.append('expected_route_km', expectedLength);
      formData.append('jumper_excluded_m', '0.0');
      formData.append('graph_reach_tolerance_km', '0.030');
      formData.append('event_shortfall_tolerance_km', '0.500');
      formData.append('overlength_tolerance_km', '0.500');

      formData.append('segment_start_km', segmentStart);
      formData.append('segment_end_km', segmentEnd);
      formData.append('section_export_scope', sectionExportScope);
      formData.append('section_merge_tolerance_m', sectionMergeTolerance);
      formData.append('section_min_length_km', sectionMinLength);
      formData.append('section_event_source', sectionEventSource);
      formData.append('section_boundary_priority', sectionBoundaryPriority);
      formData.append('section_allow_split', sectionAllowSplit);
      formData.append('section_match_tolerance_m', sectionMatchTolerance);
      formData.append('section_measurement_mode', sectionMeasurementMode);

      formData.append('output_mode', outputMode);
      formData.append('exporter_name', exportData.exporterName);
      formData.append('unit', exportData.exporterUnit);
      formData.append('route_name', exportData.exportRoute);
      formData.append('stv_total_core', stvTotalCore);
      formData.append('stv_used_core', stvUsedCore);

      setStatus({ message: 'Đang xử lý báo cáo...', type: 'info' });
      const controller = new AbortController();
      const timeoutId = window.setTimeout(
        () => controller.abort(),
        REPORT_PROCESSING_TIMEOUT_MS,
      );
      let response: Response;
      try {
        response = await fetch('/trace/convert-from-blob', {
          method: 'POST',
          body: formData,
          signal: controller.signal,
        });
      } catch (error) {
        if (error instanceof Error && error.name === 'AbortError') {
          throw new Error(
            'Quá thời gian xử lý 3 phút. Báo cáo chưa được đánh dấu thành công.',
          );
        }
        throw error;
      } finally {
        window.clearTimeout(timeoutId);
      }
      const converted = await parseStorageConversionResponse(response);
      setReadyReport(converted);
      setStatus({ message: 'Đang tự động tải báo cáo...', type: 'info' });
      try {
        const signedDownload = await requestSignedDownload(
          converted.output_pathname,
        );
        downloadFromSignedUrl(
          signedDownload.download_url,
          converted.filename,
        );
        setStatus({
          message: `Đã gửi yêu cầu tải tự động ${converted.filename} tới trình duyệt. Nếu chưa thấy file, nhấn “Tải báo cáo”.`,
          type: 'success',
        });
      } catch (downloadError) {
        setStatus({
          message: downloadError instanceof Error
            ? `Báo cáo đã sẵn sàng nhưng chưa thể tải tự động: ${downloadError.message} Nhấn “Tải báo cáo” để thử lại.`
            : 'Báo cáo đã sẵn sàng nhưng chưa thể tải tự động. Nhấn “Tải báo cáo” để thử lại.',
          type: 'error',
        });
      }
    } catch (err: any) {
      setStatus({
        message: err instanceof Error ? err.message : 'Có lỗi xảy ra khi xử lý file.',
        type: 'error',
      });
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDownloadReadyReport = async () => {
    if (!readyReport) return;
    setStatus({ message: 'Đang tạo liên kết tải báo cáo...', type: 'info' });
    try {
      const signedDownload = await requestSignedDownload(
        readyReport.output_pathname,
      );
      downloadFromSignedUrl(signedDownload.download_url, readyReport.filename);
      setStatus({
        message: `Đã gửi yêu cầu tải ${readyReport.filename} tới trình duyệt.`,
        type: 'success',
      });
    } catch (error) {
      setStatus({
        message: error instanceof Error
          ? error.message
          : 'Không thể tạo liên kết tải báo cáo.',
        type: 'error',
      });
    }
  };

  return (
    <div className="flex-1 flex flex-col min-w-0 p-margin-mobile md:p-8 gap-8 pb-24">
      <section className="opacity-0 animate-fade-up" style={{ animationFillMode: 'forwards' }}>
        <h1 className="font-headline-xl text-[28px] md:text-headline-xl text-industrial-navy mb-2 tracking-tight">Cấu hình Xuất Excel Tuyến</h1>
        <p className="font-body-md text-on-surface-variant max-w-2xl leading-relaxed">Chuẩn hóa dữ liệu đo OTDR sang báo cáo kiểm tra tuyến chuyên nghiệp. Hỗ trợ đầy đủ định dạng .SOR, .MSOR và .TRC.</p>
      </section>

      <section className="opacity-0 animate-fade-up stagger-1" style={{ animationFillMode: 'forwards' }}>
        <div
          className={`group relative w-full h-56 md:h-64 rounded-2xl border-2 border-dashed ${isDragging ? 'border-primary bg-primary/10' : 'border-primary/30 bg-surface-container-lowest'} hover:bg-primary/5 hover:border-primary transition-all flex flex-col items-center justify-center cursor-pointer overflow-hidden`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            type="file"
            ref={fileInputRef}
            multiple
            accept=".sor,.msor,.trc"
            style={{ display: 'none' }}
            onChange={handleFileSelect}
          />
          <div className="absolute inset-0 shimmer-effect opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"></div>
          <div className="bg-white p-5 rounded-2xl shadow-sm border border-outline-variant group-hover:border-primary/50 group-hover:scale-110 transition-all duration-500 z-10">
            <span className="material-symbols-outlined text-[40px] text-primary">cloud_upload</span>
          </div>
          <h3 className="font-headline-md text-[20px] text-industrial-navy mt-4 mb-1 z-10">Kéo thả tệp đo tại đây</h3>
          <p className="font-body-sm text-on-surface-variant z-10 mb-6">Hệ thống tự động phân loại định dạng</p>
          <div className="flex gap-3 z-10">
            <span className="px-3 py-1 rounded bg-white border border-outline-variant font-mono-data text-[11px] font-bold text-industrial-gray">.SOR</span>
            <span className="px-3 py-1 rounded bg-white border border-outline-variant font-mono-data text-[11px] font-bold text-industrial-gray">.MSOR</span>
            <span className="px-3 py-1 rounded bg-white border border-outline-variant font-mono-data text-[11px] font-bold text-industrial-gray">.TRC</span>
          </div>
        </div>

        {files.length > 0 && (
          <div className="mt-3 bg-white border border-outline-variant rounded-xl p-4 shadow-sm max-h-48 overflow-y-auto">
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm font-bold text-industrial-navy">{files.length} file đã chọn</span>
              <button onClick={clearFiles} className="text-xs text-error hover:underline">Xóa tất cả</button>
            </div>
            <ul className="flex flex-col gap-1">
              {files.map((f, idx) => (
                <li key={idx} className="flex justify-between items-center text-sm p-1.5 hover:bg-surface-container rounded-md">
                  <span className="truncate max-w-[80%] font-medium text-on-surface">{f.name}</span>
                  <button onClick={() => removeFile(idx)} className="text-on-surface-variant hover:text-error">
                    <span className="material-symbols-outlined text-[18px]">close</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {status && (
          <div className={`mt-4 p-4 rounded-xl text-sm font-medium ${status.type === 'error' ? 'bg-error-container text-on-error-container border border-error/20' : status.type === 'success' ? 'bg-green-100 text-green-800 border border-green-200' : 'bg-blue-100 text-blue-800 border border-blue-200'}`}>
            {status.message}
          </div>
        )}
        {readyReport && (
          <button
            type="button"
            onClick={handleDownloadReadyReport}
            className="mt-3 px-5 py-3 rounded-xl bg-primary text-white font-bold hover:bg-industrial-navy transition-colors"
          >
            Tải báo cáo
          </button>
        )}
      </section>

      {/* Configuration Settings Panel */}
      <section className="glass-card rounded-2xl overflow-hidden flex flex-col opacity-0 animate-fade-up stagger-3 border border-outline-variant shadow-sm" style={{ animationFillMode: 'forwards' }}>
        <div className="p-8 flex flex-col gap-6 w-full">
          {/* QUICK PRESETS ROW */}
          <div className="flex flex-col gap-2">
            <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Chọn nhanh cấu hình mẫu (Preset):</label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <button type="button" onClick={() => applyPreset('compact')} className="p-3 text-left rounded-xl border border-outline-variant bg-white hover:bg-surface-container transition-all">
                <span className="block font-bold text-sm text-industrial-navy">Báo cáo gọn</span>
                <span className="block text-[11px] text-on-surface-variant font-medium">Ít mốc hơn, bảng ngắn hơn.</span>
              </button>
              <button type="button" onClick={() => applyPreset('daily')} className="p-3 text-left rounded-xl border border-outline-variant bg-white hover:bg-surface-container transition-all">
                <span className="block font-bold text-sm text-industrial-navy">Vận hành hằng ngày</span>
                <span className="block text-[11px] text-on-surface-variant font-medium">Cân bằng, khuyên dùng.</span>
              </button>
              <button type="button" onClick={() => applyPreset('detailed')} className="p-3 text-left rounded-xl border border-outline-variant bg-white hover:bg-surface-container transition-all">
                <span className="block font-bold text-sm text-industrial-navy">Soi kỹ tuyến</span>
                <span className="block text-[11px] text-on-surface-variant font-medium">Giữ nhiều mốc để xem chi tiết.</span>
              </button>
              <button type="button" onClick={() => applyPreset('range')} className="p-3 text-left rounded-xl border border-outline-variant bg-white hover:bg-surface-container transition-all">
                <span className="block font-bold text-sm text-industrial-navy">Kiểm tra theo đoạn</span>
                <span className="block text-[11px] text-on-surface-variant font-medium">Chỉ phân tích đoạn được chọn.</span>
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {/* BASIC FIELDS */}
            <div className="space-y-2">
              <div className="flex justify-between items-end">
                <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Ngưỡng Event</label>
                <span className="text-[11px] font-bold text-on-surface-variant px-1.5 py-0.5 bg-surface-container-high rounded font-mono-data">dB</span>
              </div>
              <input value={threshold} onChange={(e) => setThreshold(e.target.value)} className="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" step="0.01" type="number" />
              <p className="text-[11px] text-on-surface-variant font-medium">Chỉ phân tích các sự kiện có suy hao vượt ngưỡng này.</p>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between items-end">
                <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Ngưỡng Section Loss</label>
                <span className="text-[11px] font-bold text-on-surface-variant px-1.5 py-0.5 bg-surface-container-high rounded font-mono-data">dB/km</span>
              </div>
              <input value={sectionThreshold} onChange={(e) => setSectionThreshold(e.target.value)} className="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none placeholder:text-outline" placeholder="Tự động" step="0.01" type="number" />
              <p className="text-[11px] text-on-surface-variant font-medium">Cảnh báo đỏ nếu suy hao trung bình vượt ngưỡng thiết lập.</p>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between items-end">
                <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Thời gian đo (Duration)</label>
                <span className="text-[11px] font-bold text-on-surface-variant px-1.5 py-0.5 bg-surface-container-high rounded font-mono-data">Giây</span>
              </div>
              <input value={durationThreshold} onChange={(e) => setDurationThreshold(e.target.value)} className="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" step="1" type="number" />
              <p className="text-[11px] text-on-surface-variant font-medium">Đánh dấu không đạt (Fail) nếu thời gian đo thực tế thấp hơn.</p>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between items-end">
                <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Dung sai gom cụm</label>
                <span className="text-[11px] font-bold text-on-surface-variant px-1.5 py-0.5 bg-surface-container-high rounded font-mono-data">Mét</span>
              </div>
              <input value={deviation} onChange={(e) => setDeviation(e.target.value)} className="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" step="1" type="number" />
              <p className="text-[11px] text-on-surface-variant font-medium">Khoảng cách tối đa để gộp các điểm suy hao gần nhau.</p>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between items-end">
                <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Chiều dài tuyến chuẩn</label>
                <span className="text-[11px] font-bold text-on-surface-variant px-1.5 py-0.5 bg-surface-container-high rounded font-mono-data">km</span>
              </div>
              <input value={expectedLength} onChange={(e) => setExpectedLength(e.target.value)} className="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none placeholder:text-outline" placeholder="Ví dụ: 38.800" step="0.001" type="number" />
              <p className="text-[11px] text-on-surface-variant font-medium">Nhập chiều dài thiết kế để đối chiếu kiểm thử.</p>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between items-end">
                <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Sai số đủ tuyến</label>
                <span className="text-[11px] font-bold text-on-surface-variant px-1.5 py-0.5 bg-surface-container-high rounded font-mono-data">km</span>
              </div>
              <input value={routeTolerance} onChange={(e) => setRouteTolerance(e.target.value)} className="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" step="0.001" type="number" />
              <p className="text-[11px] text-on-surface-variant font-medium">Dung sai độ lệch chiều dài cho phép.</p>
            </div>

            <div className="space-y-2">
              <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Kiểu file đầu ra</label>
              <select value={outputMode} onChange={(e) => setOutputMode(e.target.value)} className="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none">
                <option value="fastreporter">FastReporter OTDR Cable (Chuẩn FPT)</option>
                <option value="stv">Bảng sự kiện kiểm tra tuyến (STV)</option>
              </select>
              <p className="text-[11px] text-on-surface-variant font-medium">Chọn mẫu định dạng file xuất ra.</p>
            </div>

            {/* Core inputs are shared by both basic and advanced modes. */}
            <div className="space-y-2">
              <div className="border border-outline-variant rounded-xl overflow-hidden">
                <div className="px-4 py-2.5 bg-surface-container-high border-b border-outline-variant">
                  <span className="text-[11px] font-bold text-industrial-navy uppercase tracking-widest">Thông số Core</span>
                </div>
                <div className="grid grid-cols-2 divide-x divide-outline-variant">
                  <div className="p-3 space-y-1.5">
                    <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider block">Tổng core</label>
                    <input value={stvTotalCore} onChange={(e) => setStvTotalCore(e.target.value)} className="w-full bg-white border border-outline-variant rounded-lg px-3 py-2.5 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none placeholder:text-outline" type="number" min="1" step="1" placeholder="VD: 24" />
                    <p className="text-[10px] text-on-surface-variant leading-tight">Tổng số core cáp. Để trống = tự tính theo số file.</p>
                  </div>
                  <div className="p-3 space-y-1.5">
                    <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider block">Core sử dụng</label>
                    <input value={stvUsedCore} onChange={(e) => setStvUsedCore(e.target.value)} className="w-full bg-white border border-outline-variant rounded-lg px-3 py-2.5 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none placeholder:text-outline" type="number" min="0" step="1" placeholder="VD: 4" />
                    <p className="text-[10px] text-on-surface-variant leading-tight">Core đang khai thác. Để trống = tự tính.</p>
                  </div>
                </div>
              </div>
            </div>

            {/* ADVANCED FIELDS */}
            <div className={`space-y-2 ${activeTab === 'basic' ? 'hidden' : ''}`}>
              <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Xuất section theo</label>
              <select value={sectionExportScope} onChange={(e) => {
                const nextScope = e.target.value;
                setSectionExportScope(nextScope);
                if (nextScope !== 'selected_range') {
                  setSegmentStart('');
                  setSegmentEnd('');
                }
              }} className="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none">
                <option value="all">Toàn bộ tuyến đo được</option>
                <option value="selected_range">Chỉ đoạn đã chọn (Từ mốc bắt đầu -{'>'} kết thúc)</option>
              </select>
              <p className="text-[11px] text-on-surface-variant font-medium">Phạm vi xuất dữ liệu của sheet Sections.</p>
            </div>

            <div className={`space-y-2 ${activeTab === 'basic' ? 'hidden' : ''}`}>
              <div className="flex justify-between items-end">
                <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Đoạn bắt đầu</label>
                <span className="text-[11px] font-bold text-on-surface-variant px-1.5 py-0.5 bg-surface-container-high rounded font-mono-data">km</span>
              </div>
              <input value={segmentStart} onChange={(e) => setSegmentStart(e.target.value)} className="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none placeholder:text-outline" placeholder="Ví dụ: 38.000" step="0.001" type="number" />
              <p className="text-[11px] text-on-surface-variant font-medium">Điểm đầu phân tích đoạn riêng.</p>
            </div>

            <div className={`space-y-2 ${activeTab === 'basic' ? 'hidden' : ''}`}>
              <div className="flex justify-between items-end">
                <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Đoạn kết thúc</label>
                <span className="text-[11px] font-bold text-on-surface-variant px-1.5 py-0.5 bg-surface-container-high rounded font-mono-data">km</span>
              </div>
              <input value={segmentEnd} onChange={(e) => setSegmentEnd(e.target.value)} className="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none placeholder:text-outline" placeholder="Ví dụ: 40.000" step="0.001" type="number" />
              <p className="text-[11px] text-on-surface-variant font-medium">Điểm cuối phân tích đoạn riêng.</p>
            </div>

            <div className={`space-y-2 ${activeTab === 'basic' ? 'hidden' : ''}`}>
              <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Độ chi tiết bảng Section</label>
              <select value={sectionDetailLevel} onChange={(e) => setSectionDetailLevel(e.target.value)} className="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none">
                <option value="maximum">Tối đa (Nhiều mốc sự kiện nhất)</option>
                <option value="balanced">Vừa phải (Khuyên dùng)</option>
                <option value="minimum">Tối thiểu (Chỉ mốc chính)</option>
              </select>
              <p className="text-[11px] text-on-surface-variant font-medium">Quyết định mật độ mốc phân chia.</p>
            </div>

            <div className={`space-y-2 ${activeTab === 'basic' ? 'hidden' : ''}`}>
              <div className="flex justify-between items-end">
                <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Sai số gom đoạn</label>
                <span className="text-[11px] font-bold text-on-surface-variant px-1.5 py-0.5 bg-surface-container-high rounded font-mono-data">m</span>
              </div>
              <input value={sectionMergeTolerance} onChange={(e) => setSectionMergeTolerance(e.target.value)} className="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" step="1" type="number" />
              <p className="text-[11px] text-on-surface-variant font-medium">Khoảng cách tối đa gộp mốc gần nhau.</p>
            </div>

            <div className={`space-y-2 ${activeTab === 'basic' ? 'hidden' : ''}`}>
              <div className="flex justify-between items-end">
                <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Chiều dài đoạn tối thiểu</label>
                <span className="text-[11px] font-bold text-on-surface-variant px-1.5 py-0.5 bg-surface-container-high rounded font-mono-data">km</span>
              </div>
              <input value={sectionMinLength} onChange={(e) => setSectionMinLength(e.target.value)} className="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" step="0.1" type="number" />
              <p className="text-[11px] text-on-surface-variant font-medium">Bỏ qua đoạn chia nhỏ hơn chiều dài này.</p>
            </div>

            <div className={`space-y-2 ${activeTab === 'basic' ? 'hidden' : ''}`}>
              <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Lấy mốc chia đoạn</label>
              <select value={sectionEventSource} onChange={(e) => setSectionEventSource(e.target.value)} className="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none">
                <option value="all">Tất cả mốc sự kiện (Suy hao + Phản xạ)</option>
                <option value="loss">Chỉ các mốc suy hao</option>
                <option value="reflectance">Chỉ các mốc phản xạ</option>
              </select>
              <p className="text-[11px] text-on-surface-variant font-medium">Sự kiện làm ranh giới mốc đoạn.</p>
            </div>

            <div className={`space-y-2 ${activeTab === 'basic' ? 'hidden' : ''}`}>
              <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Ưu tiên nguồn chia đoạn</label>
              <select value={sectionBoundaryPriority} onChange={(e) => setSectionBoundaryPriority(e.target.value)} className="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none">
                <option value="event">Ưu tiên mốc sự kiện quang</option>
                <option value="preset">Ưu tiên mốc thiết lập trước</option>
              </select>
              <p className="text-[11px] text-on-surface-variant font-medium">Phương án giải quyết xung đột ranh giới.</p>
            </div>

            <div className={`space-y-2 ${activeTab === 'basic' ? 'hidden' : ''}`}>
              <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Cho phép chia nhỏ đoạn</label>
              <select value={sectionAllowSplit} onChange={(e) => setSectionAllowSplit(e.target.value)} className="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none">
                <option value="false">Không chia nhỏ (Khuyên dùng)</option>
                <option value="true">Tự động chia nhỏ khi đoạn quá dài</option>
              </select>
              <p className="text-[11px] text-on-surface-variant font-medium">Thêm mốc nhân tạo nếu khoảng cách quá dài.</p>
            </div>

            <div className={`space-y-2 ${activeTab === 'basic' ? 'hidden' : ''}`}>
              <div className="flex justify-between items-end">
                <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Sai số so khớp</label>
                <span className="text-[11px] font-bold text-on-surface-variant px-1.5 py-0.5 bg-surface-container-high rounded font-mono-data">m</span>
              </div>
              <input value={sectionMatchTolerance} onChange={(e) => setSectionMatchTolerance(e.target.value)} className="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-mono-data text-lg text-industrial-navy focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none" step="1" type="number" />
              <p className="text-[11px] text-on-surface-variant font-medium">Dung sai định danh trùng khớp sự kiện.</p>
            </div>

            <div className={`space-y-2 ${activeTab === 'basic' ? 'hidden' : ''}`}>
              <label className="text-[13px] font-bold text-industrial-navy uppercase tracking-wider">Cách tính suy hao Section</label>
              <select value={sectionMeasurementMode} onChange={(e) => setSectionMeasurementMode(e.target.value)} className="w-full bg-white border border-outline-variant rounded-lg px-4 py-3 font-body-sm text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none">
                <option value="fit">Tự động khớp tuyến tính LSA</option>
                <option value="two_point">Phương pháp 2 điểm (Simple 2-Point)</option>
              </select>
              <p className="text-[11px] text-on-surface-variant font-medium">Công thức toán học ước lượng suy hao riêng đoạn.</p>
            </div>

          </div>
        </div>
      </section>

      {/* Action Area */}
      <section className="opacity-0 animate-fade-up stagger-4" style={{ animationFillMode: 'forwards' }}>
        <button
          onClick={handleExportClick}
          disabled={isProcessing}
          className="group w-full h-20 bg-industrial-navy hover:bg-primary disabled:opacity-60 disabled:cursor-not-allowed text-white rounded-2xl font-headline-md text-[20px] flex items-center justify-center gap-4 transition-all active:scale-[0.98] shadow-xl shadow-primary/20 btn-pro relative overflow-hidden"
        >
          <div className="absolute inset-0 shimmer-effect opacity-20 pointer-events-none"></div>
          <span className="material-symbols-outlined text-[32px]">table_view</span>
          <span className="tracking-tight">
            {isProcessing ? 'ĐANG XỬ LÝ BÁO CÁO' : 'XUẤT BÁO CÁO EXCEL'}
          </span>
          <span className="material-symbols-outlined text-[20px] opacity-0 group-hover:opacity-100 group-hover:translate-x-2 transition-all">arrow_forward</span>
        </button>
        <div className="flex items-center justify-center gap-2 mt-4 text-on-surface-variant">
          <span className="material-symbols-outlined text-[16px]">verified</span>
          <p className="text-[12px] font-bold uppercase tracking-wider">Hệ thống sẵn sàng tạo file theo cấu hình hiện tại</p>
        </div>
      </section>

      <Modals
        isExportModalOpen={isExportModalOpen}
        setIsExportModalOpen={setIsExportModalOpen}
        onConfirmExport={handleConfirmExport}
      />
    </div>
  );
};

export default TraceViewer;
