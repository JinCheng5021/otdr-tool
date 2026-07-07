import React, { useState, useRef } from 'react';
import ReactECharts from 'echarts-for-react';
import { exportToPdf } from './exportPdf';
import './App.css';

import { SharedLayoutProps, Trace } from './types';

const EventIcon: React.FC<{ type: string }> = ({ type }) => {
  let pathD = "M 0 12 L 24 12"; // Default straight line
  if (type === 'reflective') {
    pathD = "M 0 14 L 8 14 L 12 2 L 16 14 L 24 14"; // Peak
  } else if (type === 'non-reflective') {
    pathD = "M 0 8 L 10 8 L 14 16 L 24 16"; // Splice drop
  }
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" style={{ verticalAlign: 'middle', marginRight: 4 }}>
      <path d={pathD} fill="none" stroke="blue" strokeWidth="1.5" />
    </svg>
  );
};

const MobileLayout: React.FC<SharedLayoutProps> = ({
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
  const [showInfo, setShowInfo] = useState<boolean>(false);

  const [isDraggingGlobal, setIsDraggingGlobal] = useState<boolean>(false);
  const [showUploadModal, setShowUploadModal] = useState<boolean>(false);
  const [isDraggingLocal, setIsDraggingLocal] = useState<boolean>(false);
  const dragCounter = useRef(0);

  const echartsRef = useRef<any>(null);

  const handleFilesLocal = async (files: FileList) => {
    setShowInfo(false);
    setShowUploadModal(false);
    await handleFiles(files);
  };

  const handleFileUploadLocal = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) {
      handleFilesLocal(event.target.files);
      event.target.value = '';
    }
  };

  const onDragEnterGlobal = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current++;
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDraggingGlobal(true);
    }
  };

  const onDragLeaveGlobal = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current--;
    if (dragCounter.current === 0) {
      setIsDraggingGlobal(false);
    }
  };

  const onDragOverGlobal = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const onDropGlobal = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingGlobal(false);
    dragCounter.current = 0;

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFilesLocal(e.dataTransfer.files);
    }
  };

  const renderDropzone = () => (
    <div
      className={`dropzone ${isDraggingLocal ? 'drag-active' : ''}`}
      onDragEnter={(e) => { e.preventDefault(); e.stopPropagation(); setIsDraggingLocal(true); }}
      onDragLeave={(e) => { e.preventDefault(); e.stopPropagation(); setIsDraggingLocal(false); }}
      onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
      onDrop={(e) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDraggingLocal(false);
        setIsDraggingGlobal(false);
        dragCounter.current = 0;
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
          handleFilesLocal(e.dataTransfer.files);
        }
      }}
      onClick={() => {
        const fileInput = document.getElementById('dropzone-file-input') as HTMLInputElement;
        if (fileInput) fileInput.click();
      }}
    >
      <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
        <polyline points="17 8 12 3 7 8"></polyline>
        <line x1="12" y1="3" x2="12" y2="15"></line>
      </svg>
      <h2>Kéo thả file vào đây</h2>
      <p>Hoặc click để chọn file OTDR (.sor, .msor)</p>
      <input
        id="dropzone-file-input"
        type="file"
        multiple
        accept=".sor,.msor,.trc"
        style={{ display: 'none' }}
        onChange={handleFileUploadLocal}
      />
    </div>
  );

  const handleResetZoom = () => {
    if (echartsRef.current) {
      const echartInstance = echartsRef.current.getEchartsInstance();
      echartInstance.dispatchAction({
        type: 'dataZoom',
        start: 0,
        end: 100
      });
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setCurrentFileIndex(Number(e.target.value));
    setSelectedEvent(null);
    handleResetZoom();
  };

  const currentApiData = apiDataList.length > 0 ? apiDataList[currentFileIndex] : null;

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
          fontSize: 11,
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
        lineStyle: {
          color: '#1f77b4',
          width: 2
        },
        markPoint: {
          symbol: 'path://M 46 0 L 54 0 L 54 80 L 100 100 L 0 100 L 46 80 Z',
          symbolSize: [14, 60],
          symbolOffset: [0, '15%'],
          itemStyle: {
            color: 'transparent',
            borderColor: '#1f77b4',
            borderWidth: 1.5
          },
          emphasis: {
            itemStyle: { color: 'rgba(31, 119, 180, 0.1)', borderColor: '#d62728', borderWidth: 2 },
            symbolSize: [16, 65],
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
      grid: {
        top: 20,
        bottom: 30,
        left: 40,
        right: 20
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        showContent: false
      },
      xAxis: { type: 'value', name: 'km', nameGap: 5, scale: true },
      yAxis: { type: 'value', name: 'dB', nameGap: 5, scale: true },
      dataZoom: [
        { type: 'inside', xAxisIndex: 0 },
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
        startValue: Math.max(0, ev.distance_km - 0.3),
        endValue: ev.distance_km + 0.3
      });
    }
  };

  return (
    <div
      className="app-container"
      onDragEnter={onDragEnterGlobal}
      onDragLeave={onDragLeaveGlobal}
      onDragOver={onDragOverGlobal}
      onDrop={onDropGlobal}
    >
      {isDraggingGlobal && (
        <div className="global-drag-overlay">
          <div className="global-drag-overlay-content">
            <svg width="80" height="80" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
              <polyline points="17 8 12 3 7 8"></polyline>
              <line x1="12" y1="3" x2="12" y2="15"></line>
            </svg>
            <h2>Thả file vào đây để tải lên...</h2>
          </div>
        </div>
      )}

      {showUploadModal && (
        <div className="upload-modal-overlay" onClick={() => setShowUploadModal(false)}>
          <div className="upload-modal-content" onClick={e => e.stopPropagation()}>
            <button className="upload-modal-close" onClick={() => setShowUploadModal(false)}>&times;</button>
            {renderDropzone()}
          </div>
        </div>
      )}
      {/* TẦNG 1: TOP HEADER */}
      <div className="top-header">
        <div className="header-row">
          <div className="file-name" title={currentApiData?.filename || 'Chưa tải file'}>
            {apiDataList.length > 1 ? (
              <select className="file-dropdown" value={currentFileIndex} onChange={handleFileChange}>
                {apiDataList.map((data, idx) => (
                  <option key={idx} value={idx}>{data.filename}</option>
                ))}
              </select>
            ) : (
              currentApiData ? currentApiData.filename : 'Chưa tải file OTDR'
            )}
          </div>

          <div className="header-actions">
            {currentApiData && (
              <button className="icon-btn-danger" onClick={handleDeleteCurrentFile} title="Xóa file này">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="3 6 5 6 21 6"></polyline>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                  <line x1="10" y1="11" x2="10" y2="17"></line>
                  <line x1="14" y1="11" x2="14" y2="17"></line>
                </svg>
              </button>
            )}
            
            {currentApiData && (
              <button 
                className="icon-btn" 
                title="Xuất báo cáo PDF" 
                onClick={() => exportToPdf(currentApiData, getChartOptions(), currentApiData.filename)}
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                  <polyline points="7 10 12 15 17 10"></polyline>
                  <line x1="12" y1="15" x2="12" y2="3"></line>
                </svg>
              </button>
            )}

            <div className="upload-btn-wrapper">
              <button className="icon-btn" title="Tải file mới" onClick={() => setShowUploadModal(true)}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                  <polyline points="17 8 12 3 7 8"></polyline>
                  <line x1="12" y1="3" x2="12" y2="15"></line>
                </svg>
              </button>
            </div>

            {currentApiData && (
              <button className="icon-btn" onClick={() => setShowInfo(!showInfo)} title="Thông số vật lý">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10"></circle>
                  <line x1="12" y1="16" x2="12" y2="12"></line>
                  <line x1="12" y1="8" x2="12.01" y2="8"></line>
                </svg>
              </button>
            )}
          </div>
        </div>

        {currentApiData && currentApiData.traces.length > 0 && (
          <div className="stats-row">
            <div className="stat-box">
              <span className="stat-label">Chiều dài tuyến</span>
              <span className="stat-value">
                {currentApiData.traces[0].metadata.fiber_length === 0 ? '' : `${(currentApiData.traces[0].metadata.fiber_length / 1000).toFixed(3)} km`}
              </span>
            </div>
            <div className="stat-box">
              <span className="stat-label">Tổng suy hao</span>
              <span className="stat-value">
                {currentApiData.traces[0].metadata.total_loss === 0 ? '' : `${currentApiData.traces[0].metadata.total_loss.toFixed(3)} dB`}
              </span>
            </div>
          </div>
        )}

        {showInfo && currentApiData && (
          <div className="info-popover">
            <p><span>Ngày đo:</span> {currentApiData.traces[0].metadata.measurement_date}</p>
            <p><span>Loại máy:</span> {currentApiData.traces[0].metadata.machine_type}</p>
            <p><span>Bước sóng:</span> {currentApiData.traces[0].metadata.wavelength}</p>
            <p><span>Xung:</span> {currentApiData.traces[0].metadata.pulse_width}</p>
            <p><span>IOR:</span> {currentApiData.traces[0].metadata.index_of_refraction}</p>
          </div>
        )}
      </div>

      {loading && (
        <div className="empty-state">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#1f77b4" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ animation: 'App-logo-spin infinite 2s linear' }}>
            <path d="M21 12a9 9 0 1 1-6.219-8.56"></path>
          </svg>
          <p>Đang xử lý...</p>
        </div>
      )}

      {!loading && !currentApiData && (
        <div className="empty-state">
          {renderDropzone()}
        </div>
      )}

      {currentApiData && currentApiData.traces.length > 0 && !loading && (
        <>
          {/* TẦNG 2: CHART */}
          <div className="chart-container">
            <div className="chart-tools">
              <button className="tool-btn" onClick={handleResetZoom}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="1 4 1 10 7 10"></polyline>
                  <polyline points="23 20 23 14 17 14"></polyline>
                  <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10M23 14l-4.64 4.36A9 9 0 0 1 3.51 15"></path>
                </svg>
                Reset Zoom
              </button>
            </div>
            <ReactECharts
              ref={echartsRef}
              option={getChartOptions()}
              onEvents={onChartEvents}
              style={{ height: '100%', width: '100%' }}
            />
          </div>

          {/* TẦNG 3: EVENT DETAILS */}
          <div className="event-details">
            {selectedEvent ? (
              <div className="event-grid">
                <div className="detail-item">
                  <span className="detail-label">{selectedEvent.name}</span>
                  <span className="detail-value">{selectedEvent.type}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Vị trí</span>
                  <span className="detail-value">{Number(selectedEvent.distance) === 0 ? '' : `${selectedEvent.distance} km`}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Suy hao điểm</span>
                  <span className={`detail-value ${Number(selectedEvent.splice_loss) > 0.5 ? 'value-red' : ''}`}>
                    {Number(selectedEvent.splice_loss) === 0 ? '' : `${Number(selectedEvent.splice_loss).toFixed(3)} dB`}
                  </span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Phản xạ</span>
                  <span className="detail-value">
                    {selectedEvent.reflectance == null || Number(selectedEvent.reflectance) === 0 ? '' : `${Number(selectedEvent.reflectance).toFixed(3)} dB`}
                  </span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Hệ số suy hao</span>
                  <span className="detail-value">{Number(selectedEvent.slope) === 0 ? '' : `${Number(selectedEvent.slope).toFixed(3)} dB/km`}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Section Loss</span>
                  <span className="detail-value">{Number(selectedEvent.section_loss) === 0 ? '' : `${Number(selectedEvent.section_loss).toFixed(3)} dB`}</span>
                </div>
              </div>
            ) : (
              <div style={{ color: '#888', fontSize: 13, textAlign: 'center', marginTop: 10 }}>
                Chạm vào sự kiện trên biểu đồ hoặc danh sách để xem chi tiết
              </div>
            )}
          </div>

          {/* TẦNG 4: EVENT LIST */}
          <div className="event-list-container">
            <div className="list-title">Danh sách sự kiện</div>
            <div className="table-responsive">
              <table className="event-table">
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
          </div>
        </>
      )}
    </div>
  );
};

export default MobileLayout;