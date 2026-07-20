import React, { useCallback, useEffect, useRef, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { SharedLayoutProps, Trace } from '../../types';
import { exportToPdf } from '../../exportPdf';
import '../../App.css';
import './DesktopLayout.css';

const EventIcon: React.FC<{ type: string }> = ({ type }) => {
  let pathD = "M 0 12 L 24 12";
  if (type === 'reflective') {
    pathD = "M 0 14 L 8 14 L 12 2 L 16 14 L 24 14";
  } else if (type === 'non-reflective') {
    pathD = "M 0 8 L 10 8 L 14 16 L 24 16";
  }
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" style={{ verticalAlign: 'middle', marginRight: 4 }}>
      <path d={pathD} fill="none" stroke="blue" strokeWidth="1.5" />
    </svg>
  );
};

// ─── Zoom Icon SVG ─────────────────────────────────────────────────────────────
const ZoomIcon: React.FC<{ size?: number }> = ({ size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="8" />
    <line x1="21" y1="21" x2="16.65" y2="16.65" />
    <line x1="11" y1="8" x2="11" y2="14" />
    <line x1="8" y1="11" x2="14" y2="11" />
  </svg>
);

// ─── Restore Icon SVG ──────────────────────────────────────────────────────────
const RestoreIcon: React.FC<{ size?: number }> = ({ size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
    <path d="M3 3v5h5" />
  </svg>
);

// ─── Download Icon SVG ─────────────────────────────────────────────────────────
const DownloadIcon: React.FC<{ size?: number }> = ({ size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
    <polyline points="7 10 12 15 17 10"></polyline>
    <line x1="12" y1="15" x2="12" y2="3"></line>
  </svg>
);

const DesktopLayout: React.FC<SharedLayoutProps> = ({
  apiDataList,
  currentFileIndex,
  loading,
  selectedEvent,
  handleFiles,
  handleFileUpload,
  handleDeleteCurrentFile,
  setCurrentFileIndex,
  setSelectedEvent
}) => {
  const echartsRef = useRef<any>(null);
  const [isDraggingLocal, setIsDraggingLocal] = useState<boolean>(false);

  // ── Zoom mode state ──────────────────────────────────────────────────────────
  const [isZoomMode, setIsZoomMode] = useState<boolean>(false);

  // ── Resizable panel state ────────────────────────────────────────────────────
  const [sidebarWidth, setSidebarWidth] = useState<number>(260);
  const [rightPanelWidth, setRightPanelWidth] = useState<number>(320);
  const [chartHeightPercent, setChartHeightPercent] = useState<number>(65);

  // Drag refs (avoid stale closures in event listeners)
  const dragStateRef = useRef<{
    type: 'sidebar' | 'rightPanel' | 'vertical' | null;
    startX: number;
    startY: number;
    startValue: number;
    containerHeight: number;
  }>({ type: null, startX: 0, startY: 0, startValue: 0, containerHeight: 0 });

  const mainContentRef = useRef<HTMLDivElement>(null);

  const currentApiData = apiDataList.length > 0 ? apiDataList[currentFileIndex] : null;

  // ── Reset zoom when switching files ─────────────────────────────────────────
  useEffect(() => {
    setIsZoomMode(false);
  }, [currentFileIndex]);

  // ── Zoom toggle handler ──────────────────────────────────────────────────────
  const handleZoomToggle = useCallback(() => {
    if (!echartsRef.current) return;
    const echartInstance = echartsRef.current.getEchartsInstance();

    // Use functional state update to avoid stale closure
    setIsZoomMode(prev => {
      const next = !prev;
      echartInstance.dispatchAction({
        type: 'takeGlobalCursor',
        key: 'dataZoomSelect',
        dataZoomSelectActive: next
      });
      return next;
    });
  }, []);

  // ── Custom restore handler ───────────────────────────────────────────────────
  const handleRestore = useCallback(() => {
    if (!echartsRef.current) return;
    const echartInstance = echartsRef.current.getEchartsInstance();

    // Dispatch the built-in 'restore' action to natively clear the toolbox zoom history
    // and reset all dataZoom components to their initial, unzoomed states.
    echartInstance.dispatchAction({
      type: 'restore'
    });

    // Reset React zoom-mode state and cursor
    setIsZoomMode(false);
    echartInstance.dispatchAction({
      type: 'takeGlobalCursor',
      key: 'dataZoomSelect',
      dataZoomSelectActive: false
    });
  }, []);

  // ── Global mouse move/up for resize ─────────────────────────────────────────
  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      const ds = dragStateRef.current;
      if (!ds.type) return;

      if (ds.type === 'sidebar') {
        const delta = e.clientX - ds.startX;
        const next = Math.max(160, Math.min(400, ds.startValue + delta));
        setSidebarWidth(next);
      } else if (ds.type === 'rightPanel') {
        const delta = ds.startX - e.clientX;
        const next = Math.max(240, Math.min(480, ds.startValue + delta));
        setRightPanelWidth(next);
      } else if (ds.type === 'vertical') {
        const delta = e.clientY - ds.startY;
        const deltaPercent = (delta / ds.containerHeight) * 100;
        const next = Math.max(25, Math.min(80, ds.startValue + deltaPercent));
        setChartHeightPercent(next);
      }
    };

    const onMouseUp = () => {
      dragStateRef.current.type = null;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
    return () => {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    };
  }, []);

  const startSidebarResize = (e: React.MouseEvent) => {
    e.preventDefault();
    dragStateRef.current = { type: 'sidebar', startX: e.clientX, startY: 0, startValue: sidebarWidth, containerHeight: 0 };
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  const startRightPanelResize = (e: React.MouseEvent) => {
    e.preventDefault();
    dragStateRef.current = { type: 'rightPanel', startX: e.clientX, startY: 0, startValue: rightPanelWidth, containerHeight: 0 };
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  const startVerticalResize = (e: React.MouseEvent) => {
    e.preventDefault();
    const containerHeight = mainContentRef.current?.clientHeight ?? 600;
    dragStateRef.current = { type: 'vertical', startX: 0, startY: e.clientY, startValue: chartHeightPercent, containerHeight };
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
  };

  // ── Chart options ────────────────────────────────────────────────────────────
  const getChartOptions = () => {
    if (!currentApiData || currentApiData.traces.length === 0) return {};

    const seriesList = currentApiData.traces.map((trace) => {
      const markPoints = trace.events.map((ev) => ({
        name: `Sự kiện ${ev.event_number}`,
        coord: [ev.distance_km, trace.data.find(pt => pt[0] >= ev.distance_km)?.[1] || 0],
        value: ev.event_type,
        label: {
          show: true,
          position: 'bottom',
          distance: 4,
          fontSize: 12,
          fontWeight: 'bold',
          color: '#1f77b4',
          formatter: `${ev.event_number}`
        },
        eventData: ev
      }));

      return {
        name: trace.trace_name,
        type: 'line',
        showSymbol: false,
        data: trace.data,
        large: true,
        largeThreshold: 3000,
        sampling: 'lttb',
        lineStyle: { color: '#1f77b4', width: 2 },
        markPoint: {
          symbol: 'path://M 46 0 L 54 0 L 54 80 L 100 100 L 0 100 L 46 80 Z',
          symbolSize: [16, 60],
          symbolOffset: [0, '15%'],
          itemStyle: { color: 'transparent', borderColor: '#1f77b4', borderWidth: 1.5 },
          emphasis: {
            itemStyle: { color: 'rgba(31, 119, 180, 0.1)', borderColor: '#d62728', borderWidth: 2 },
            symbolSize: [18, 65],
            label: { color: '#d62728' }
          },
          tooltip: {
            show: true,
            showContent: true,
            trigger: 'item',
            triggerOn: 'click',
            formatter: (params: any) => {
              const spliceLoss = params.data.eventData.splice_loss_db || 0;
              return `<b>${params.data.name}</b><br/>Distance: ${Number(params.data.coord[0]).toFixed(3)} km<br/>Splice Loss: ${Number(spliceLoss).toFixed(3)} dB`;
            }
          },
          data: markPoints
        }
      };
    });

    return {
      grid: { top: 40, bottom: 30, left: 50, right: 30 },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        showContent: false
      },
      toolbox: {
        feature: {
          // dataZoom is kept here (with invisible icons) so that ECharts registers
          // the zoom capability — required for takeGlobalCursor to work.
          // Our custom button in the UI controls the toggle instead.
          dataZoom: {
            yAxisIndex: 'none',
            icon: {
              zoom: 'path://',  // empty path → invisible
              back: 'path://'   // empty path → invisible
            },
            iconStyle: { opacity: 0 },
            emphasis: { iconStyle: { opacity: 0 } }
          }
        },
        right: 20,
        top: 0
      },
      xAxis: { type: 'value', name: 'km', nameGap: 5, scale: true },
      yAxis: { type: 'value', name: 'dB', nameGap: 5, scale: true },
      dataZoom: [
        { type: 'inside', xAxisIndex: 0 },
        { type: 'slider', xAxisIndex: 0, bottom: 0, height: 20 }
      ],
      series: seriesList
    };
  };

  const onChartEvents = {
    click: (params: any) => {
      const echartInstance = echartsRef.current?.getEchartsInstance();

      if (params.componentType === 'markPoint') {
        setSelectedEvent({
          name: params.data.name,
          distance: Number(params.data.coord[0]).toFixed(3),
          loss_y: Number(params.data.coord[1]).toFixed(3),
          type: params.data.value,
          splice_loss: params.data.eventData.splice_loss_db,
          reflectance: params.data.eventData.reflectance_db,
          slope: params.data.eventData.slope_db_km,
          section_loss: params.data.eventData.section_loss_db
        });
      } else {
        setSelectedEvent(null);
        if (echartInstance) {
          echartInstance.dispatchAction({
            type: 'hideTip'
          });
        }
      }
    },
    'zr:click': (params: any) => {
      if (!params.target) {
        setSelectedEvent(null);
        const echartInstance = echartsRef.current?.getEchartsInstance();
        if (echartInstance) {
          echartInstance.dispatchAction({
            type: 'hideTip'
          });
        }
      }
    }
  };

  const handleRowClick = (ev: any, trace: Trace) => {
    const pt = trace.data.find(p => p[0] >= ev.distance_km);
    const loss_y = pt ? pt[1].toFixed(3) : 0;

    setSelectedEvent({
      name: `Sự kiện ${ev.event_number}`,
      distance: ev.distance_km.toFixed(4),
      loss_y: loss_y,
      type: ev.event_type,
      splice_loss: ev.splice_loss_db,
      reflectance: ev.reflectance_db,
      slope: ev.slope_db_km,
      section_loss: ev.section_loss_db
    });

    if (echartsRef.current) {
      const echartInstance = echartsRef.current.getEchartsInstance();
      echartInstance.dispatchAction({
        type: 'dataZoom',
        startValue: Math.max(0, ev.distance_km - 0.5),
        endValue: ev.distance_km + 0.5
      });
    }
  };

  // ── Render Sidebar ───────────────────────────────────────────────────────────
  const renderSidebar = () => (
    <div className="desktop-sidebar" style={{ width: sidebarWidth }}>
      <div className="sidebar-header">
        <h2>OTDR Files</h2>
        <div
          className={`sidebar-dropzone ${isDraggingLocal ? 'drag-active' : ''}`}
          onDragEnter={(e) => { e.preventDefault(); e.stopPropagation(); setIsDraggingLocal(true); }}
          onDragLeave={(e) => { e.preventDefault(); e.stopPropagation(); setIsDraggingLocal(false); }}
          onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
          onDrop={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setIsDraggingLocal(false);
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
              handleFiles(e.dataTransfer.files);
            }
          }}
          onClick={() => {
            const fileInput = document.getElementById('desktop-file-input') as HTMLInputElement;
            if (fileInput) fileInput.click();
          }}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
            <polyline points="17 8 12 3 7 8"></polyline>
            <line x1="12" y1="3" x2="12" y2="15"></line>
          </svg>
          <span>Tải file lên (Kéo thả hoặc click)</span>
          <input
            id="desktop-file-input"
            type="file"
            multiple
            accept=".sor,.msor,.trc"
            style={{ display: 'none' }}
            onChange={handleFileUpload}
          />
        </div>
      </div>
      <ul className="sidebar-file-list">
        {apiDataList.map((data, idx) => (
          <li
            key={idx}
            className={currentFileIndex === idx ? 'active' : ''}
            onClick={() => {
              setCurrentFileIndex(idx);
              setSelectedEvent(null);
            }}
          >
            <span className="file-name" title={data.filename}>{data.filename}</span>
            {currentFileIndex === idx && (
              <button
                className="delete-file-btn"
                onClick={(e) => { e.stopPropagation(); handleDeleteCurrentFile(); }}
                title="Xóa file này"
              >
                &times;
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );

  // ── Render Main Content ──────────────────────────────────────────────────────
  const renderMainContent = () => (
    <div className="desktop-main-content" ref={mainContentRef}>
      {currentApiData && currentApiData.traces.length > 0 ? (
        <>
          {/* Chart area with custom toolbar overlay */}
          <div
            className={`desktop-chart-area ${isZoomMode ? 'zoom-mode' : ''}`}
            style={{ height: `${chartHeightPercent}%` }}
          >
            {/* Custom zoom & restore buttons — overlay top-right */}
            <div className="chart-toolbar">
              <button
                className={`chart-tool-btn ${isZoomMode ? 'active' : ''}`}
                onClick={handleZoomToggle}
                title={isZoomMode ? 'Tắt zoom (bấm để kéo biểu đồ)' : 'Bật zoom (kéo để phóng to vùng)'}
              >
                <ZoomIcon />
              </button>
              <button
                className="chart-tool-btn"
                onClick={handleRestore}
                title="Khôi phục zoom về ban đầu"
              >
                <RestoreIcon />
              </button>
              <button
                className="chart-tool-btn"
                onClick={() => {
                  if (currentApiData) exportToPdf(currentApiData, getChartOptions(), currentApiData.filename);
                }}
                title="Xuất báo cáo PDF"
              >
                <DownloadIcon />
              </button>
            </div>

            <ReactECharts
              key={currentFileIndex}
              ref={echartsRef}
              option={getChartOptions()}
              onEvents={onChartEvents}
              style={{ height: '100%', width: '100%' }}
            />
          </div>

          {/* Vertical resize handle */}
          <div className="resize-handle-vertical" onMouseDown={startVerticalResize} />

          {/* Table area */}
          <div
            className="desktop-table-area"
            style={{ height: `${100 - chartHeightPercent}%` }}
          >
            <table className="desktop-event-table">
              <thead>
                <tr>
                  <th className="sticky-col">Sự kiện</th>
                  <th>Distance (km)</th>
                  <th>Loss (dB)</th>
                  <th>Reflectance (dB)</th>
                  <th>Slope (dB/km)</th>
                  <th>Section Loss (dB)</th>
                  <th>Total Loss (dB)</th>
                </tr>
              </thead>
              <tbody>
                {currentApiData.traces[0].events.map((ev, idx) => (
                  <tr
                    key={idx}
                    className={selectedEvent && selectedEvent.name === `Sự kiện ${ev.event_number}` ? 'selected' : ''}
                    onClick={() => handleRowClick(ev, currentApiData.traces[0])}
                  >
                    <td className="sticky-col">
                      <EventIcon type={ev.event_type} />
                      {ev.event_number}
                    </td>
                    <td>{Number(ev.distance_km) === 0 ? '0' : Number(ev.distance_km).toFixed(3)}</td>
                    <td className={ev.splice_loss_db > 0.5 ? 'red' : ''}>{Number(ev.splice_loss_db) === 0 ? '' : Number(ev.splice_loss_db).toFixed(3)}</td>
                    <td>{ev.reflectance_db == null || Number(ev.reflectance_db) === 0 ? '' : Number(ev.reflectance_db).toFixed(3)}</td>
                    <td>{Number(ev.slope_db_km) === 0 ? '' : Number(ev.slope_db_km).toFixed(3)}</td>
                    <td>{Number(ev.section_loss_db) === 0 ? '' : Number(ev.section_loss_db).toFixed(3)}</td>
                    <td>{Number(ev.cumulative_loss_db) === 0 ? '' : Number(ev.cumulative_loss_db).toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <div className="desktop-empty-state">
          {loading ? (
            <p>Đang tải dữ liệu...</p>
          ) : (
            <p>Chưa có file OTDR nào được chọn. Hãy tải file lên từ Sidebar bên trái.</p>
          )}
        </div>
      )}
    </div>
  );

  // ── Render Right Panel ───────────────────────────────────────────────────────
  const renderRightPanel = () => (
    <div className="desktop-right-panel" style={{ width: rightPanelWidth }}>
      <h3>Thông tin chi tiết</h3>

      {currentApiData && currentApiData.traces.length > 0 && (
        <div className="desktop-file-info">
          <h4>Thông số file</h4>
          <p><span>Chiều dài:</span> {currentApiData.traces[0].metadata.fiber_length === 0 ? '' : `${(currentApiData.traces[0].metadata.fiber_length / 1000).toFixed(3)} km`}</p>
          <p><span>Tổng suy hao:</span> {currentApiData.traces[0].metadata.total_loss === 0 ? '' : `${currentApiData.traces[0].metadata.total_loss.toFixed(3)} dB`}</p>
          <p><span>Ngày đo:</span> {currentApiData.traces[0].metadata.measurement_date}</p>
          <p><span>Máy đo:</span> {currentApiData.traces[0].metadata.machine_type}</p>
          <p><span>Bước sóng:</span> {currentApiData.traces[0].metadata.wavelength}</p>
          <p><span>Độ rộng xung:</span> {currentApiData.traces[0].metadata.pulse_width}</p>
          <p><span>IOR:</span> {currentApiData.traces[0].metadata.index_of_refraction}</p>
        </div>
      )}

      <hr />

      <div className="desktop-event-details">
        <h4>Chi tiết sự kiện</h4>
        {selectedEvent ? (
          <div className="event-info-grid">
            <div className="info-row">
              <span className="label">Tên sự kiện</span>
              <span className="value">{selectedEvent.name}</span>
            </div>
            <div className="info-row">
              <span className="label">Loại</span>
              <span className="value">{selectedEvent.type}</span>
            </div>
            <div className="info-row">
              <span className="label">Vị trí</span>
              <span className="value">{Number(selectedEvent.distance) === 0 ? '' : `${selectedEvent.distance} km`}</span>
            </div>
            <div className="info-row">
              <span className="label">Suy hao</span>
              <span className={`value ${Number(selectedEvent.splice_loss) > 0.5 ? 'value-red' : ''}`}>
                {Number(selectedEvent.splice_loss) === 0 ? '' : `${Number(selectedEvent.splice_loss).toFixed(3)} dB`}
              </span>
            </div>
            <div className="info-row">
              <span className="label">Phản xạ</span>
              <span className="value">
                {selectedEvent.reflectance == null || Number(selectedEvent.reflectance) === 0 ? '' : `${Number(selectedEvent.reflectance).toFixed(3)} dB`}
              </span>
            </div>
            <div className="info-row">
              <span className="label">Hệ số suy hao</span>
              <span className="value">{Number(selectedEvent.slope) === 0 ? '' : `${Number(selectedEvent.slope).toFixed(3)} dB/km`}</span>
            </div>
            <div className="info-row">
              <span className="label">Section Loss</span>
              <span className="value">{Number(selectedEvent.section_loss) === 0 ? '' : `${Number(selectedEvent.section_loss).toFixed(3)} dB`}</span>
            </div>
          </div>
        ) : (
          <p className="no-event">Chọn một sự kiện trên biểu đồ hoặc bảng để xem chi tiết.</p>
        )}
      </div>
    </div>
  );

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <div className="desktop-layout-container">
      {renderSidebar()}
      <div className="resize-handle" onMouseDown={startSidebarResize} />
      {renderMainContent()}
      <div className="resize-handle" onMouseDown={startRightPanelResize} />
      {renderRightPanel()}
    </div>
  );
};

export default DesktopLayout;
