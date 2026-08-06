import React, { useCallback, useState } from 'react';
import CurrentApp from './components/CurrentApp';
import TraceViewer from './components/TraceViewer';
import NotificationDropdown from './components/NotificationDropdown';
import {
  type InputFileSelection,
  selectInputFiles,
} from './components/TraceViewer/traceExport';

interface InputBatch {
  files: File[];
  revision: number;
}

const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'current' | 'traceviewer'>('traceviewer');
  const [inputBatch, setInputBatch] = useState<InputBatch>({
    files: [],
    revision: 0,
  });

  const replaceInputFiles = useCallback((incomingFiles: File[]): InputFileSelection => {
    const selection = selectInputFiles(incomingFiles);
    setInputBatch((previous) => ({
      files: selection.selectedFiles,
      revision: previous.revision + 1,
    }));
    return selection;
  }, []);

  const clearInputFiles = useCallback(() => {
    setInputBatch((previous) => ({
      files: [],
      revision: previous.revision + 1,
    }));
  }, []);

  const currentView = (
    <div
      className={
        activeTab === 'current'
          ? 'w-screen h-screen overflow-hidden bg-surface flex flex-col'
          : 'hidden'
      }
    >
      <header className="h-14 shrink-0 flex items-center gap-3 px-4 bg-white border-b border-outline-variant shadow-sm z-20">
        <button
          onClick={() => setActiveTab('traceviewer')}
          className="h-10 px-3 flex items-center gap-2 rounded-lg border border-outline-variant bg-white text-industrial-navy shadow-sm hover:bg-surface-variant hover:border-primary/30 transition-colors"
          title="Trở về Menu"
          aria-label="Trở về Menu"
        >
          <span className="material-symbols-outlined text-[22px]">arrow_back</span>
          <span className="text-sm font-semibold">Quay lại</span>
        </button>
        <div className="h-6 w-px bg-outline-variant" aria-hidden="true"></div>
        <h1 className="text-base font-semibold text-on-surface">Đồ thị tuyến</h1>
      </header>
      <div className="flex-1 min-h-0 overflow-hidden">
        <CurrentApp
          isActive={activeTab === 'current'}
          inputFiles={inputBatch.files}
          inputRevision={inputBatch.revision}
          replaceInputFiles={replaceInputFiles}
        />
      </div>
    </div>
  );

  return (
    <>
      {currentView}
      {activeTab === 'traceviewer' && (
        <div className="antialiased min-h-screen flex flex-col bg-surface text-on-background font-body-lg selection:bg-primary-fixed selection:text-on-primary-fixed">
      {/* TopAppBar */}
      <header className="bg-surface/80 backdrop-blur-md border-b border-outline-variant z-50 sticky top-0 px-margin-mobile md:px-margin-desktop w-full h-14 flex justify-between items-center">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-primary rounded flex items-center justify-center text-on-primary">
            <span className="material-symbols-outlined text-[20px]">analytics</span>
          </div>
          <span className="font-headline-md text-[18px] font-extrabold tracking-tight text-industrial-navy">FPT OTDR PRO</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-status-pass bg-status-pass/10 px-3 py-1 rounded-full border border-status-pass/20 animate-pulse-soft">
            <div className="w-2 h-2 rounded-full bg-status-pass"></div>
            <span className="text-[10px] font-bold uppercase tracking-widest">System Ready</span>
          </div>
          <NotificationDropdown />
        </div>
      </header>

      {/* Main Canvas */}
      <main className="flex-1 flex flex-col md:flex-row w-full max-w-[1400px] mx-auto relative overflow-hidden">
        {/* NavigationDrawer (Desktop Only) */}
        <aside className="hidden md:flex flex-col gap-4 p-6 bg-surface-container-low border-r border-outline-variant w-[280px] sticky top-14 h-[calc(100vh-56px)] shrink-0">
          <div className="flex flex-col gap-1">
            <nav className="flex flex-col gap-1">
              <button 
                onClick={() => setActiveTab('current')} 
                className="flex items-center gap-3 px-3 py-2 text-left rounded-lg transition-colors font-medium text-on-surface-variant hover:bg-surface-variant"
              >
                <span className="material-symbols-outlined text-[20px]">show_chart</span>
                <span className="text-sm">Đồ thị tuyến</span>
              </button>
              
              <button 
                onClick={() => setActiveTab('traceviewer')} 
                className="flex items-center gap-3 px-3 py-2 text-left rounded-lg transition-colors font-medium text-primary bg-primary-fixed/50 font-bold border border-primary/10"
              >
                <span className="material-symbols-outlined text-[20px]">tune</span>
                <span className="text-sm">Cấu hình thông số</span>
              </button>
              
              <button 
                onClick={() => window.dispatchEvent(new Event('open-history-modal'))}
                className="flex items-center gap-3 px-3 py-2 text-left rounded-lg text-on-surface-variant hover:bg-surface-variant transition-colors font-medium"
              >
                <span className="material-symbols-outlined text-[20px]">history</span>
                <span className="text-sm">Lịch sử xuất file</span>
              </button>
              <button className="flex items-center gap-3 px-3 py-2 text-left rounded-lg text-on-surface-variant hover:bg-surface-variant transition-colors font-medium">
                <span className="material-symbols-outlined text-[20px]">settings</span>
                <span className="text-sm">Tùy chọn hệ thống</span>
              </button>
            </nav>
          </div>
          
          <div className="mt-auto bg-surface-container-high/50 p-4 rounded-xl border border-outline-variant">
            <div className="flex items-center gap-2 mb-3">
              <span className="material-symbols-outlined text-[18px] text-industrial-navy">info</span>
              <span className="text-[11px] font-bold text-on-surface-variant tracking-wider uppercase">Thống kê phiên</span>
            </div>
            <ul className="space-y-3">
              <li className="flex justify-between items-center">
                <span className="text-xs text-on-surface-variant">Trace nạp:</span>
                <span className="font-mono-data text-sm font-bold text-primary">00</span>
              </li>
              <li className="flex justify-between items-center">
                <span className="text-xs text-on-surface-variant">Lỗi nhận diện:</span>
                <span className="font-mono-data text-sm font-bold text-error">00</span>
              </li>
              <li className="flex justify-between items-center">
                <span className="text-xs text-on-surface-variant">Phiên bản:</span>
                <span className="font-mono-data text-xs text-on-surface-variant">v2.1.4</span>
              </li>
            </ul>
          </div>
        </aside>

        {/* Center Visualization & Configuration Area */}
        <div className="flex-1 flex flex-col min-w-0 h-[calc(100vh-56px)] overflow-y-auto">
          <TraceViewer
            files={inputBatch.files}
            replaceInputFiles={replaceInputFiles}
            clearInputFiles={clearInputFiles}
          />
        </div>
      </main>

      {/* BottomNavBar (Mobile Only) */}
      <nav className="fixed bottom-0 w-full flex justify-around items-center h-16 bg-white/90 backdrop-blur-md z-50 md:hidden border-t border-outline-variant px-4">
        <button 
          onClick={() => setActiveTab('traceviewer')}
          className="flex flex-col items-center justify-center px-4 text-primary"
        >
          <span className="material-symbols-outlined text-[24px]">tune</span>
          <span className="text-[10px] font-bold uppercase mt-1">Cấu hình</span>
        </button>
        <button 
          onClick={() => setActiveTab('current')}
          className="flex flex-col items-center justify-center px-4 text-on-surface-variant opacity-50"
        >
          <span className="material-symbols-outlined text-[24px]">show_chart</span>
          <span className="text-[10px] font-bold uppercase mt-1">Đồ thị</span>
        </button>
        <button 
          onClick={() => window.dispatchEvent(new Event('open-history-modal'))}
          className="flex flex-col items-center justify-center px-4 text-on-surface-variant opacity-50"
        >
          <span className="material-symbols-outlined text-[24px]">history</span>
          <span className="text-[10px] font-bold uppercase mt-1">Lịch sử</span>
        </button>
      </nav>
      {/* Mobile Nav Spacing */}
      <div className="h-16 md:hidden"></div>
        </div>
      )}
    </>
  );
};

export default App;
