import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import MobileLayout from './MobileLayout';
import DesktopLayout from './DesktopLayout';
import { APIResponse } from '../../types';
import { type InputFileSelection } from '../TraceViewer/traceExport';

function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    const media = window.matchMedia(query);
    if (media.matches !== matches) {
      setMatches(media.matches);
    }
    const listener = () => setMatches(media.matches);
    media.addEventListener('change', listener);
    return () => media.removeEventListener('change', listener);
  }, [matches, query]);

  return matches;
}

interface CurrentAppProps {
  isActive: boolean;
  inputFiles: File[];
  inputRevision: number;
  replaceInputFiles: (files: File[]) => InputFileSelection;
}

const CurrentApp: React.FC<CurrentAppProps> = ({
  isActive,
  inputFiles,
  inputRevision,
  replaceInputFiles,
}) => {
  const isDesktop = useMediaQuery('(min-width: 1024px)');
  const [apiDataList, setApiDataList] = useState<APIResponse[]>([]);
  const [currentFileIndex, setCurrentFileIndex] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(false);
  const [selectedEvent, setSelectedEvent] = useState<any>(null);
  const requestRevision = useRef(0);
  const activeController = useRef<AbortController | null>(null);

  const handleFiles = async (fileList: FileList) => {
    if (!fileList || fileList.length === 0) return;
    try {
      replaceInputFiles(Array.from(fileList));
      activeController.current?.abort();
      requestRevision.current += 1;
      setApiDataList([]);
      setCurrentFileIndex(0);
      setSelectedEvent(null);
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Danh sách file không hợp lệ.');
    }
  };

  useEffect(() => {
    activeController.current?.abort();
    const revision = requestRevision.current + 1;
    requestRevision.current = revision;
    setApiDataList([]);
    setCurrentFileIndex(0);
    setSelectedEvent(null);

    if (inputFiles.length === 0) {
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    activeController.current = controller;
    const apiUrl = '/current/api/upload-otdr';
    const completedResults: APIResponse[] = [];

    const processFiles = async () => {
      setLoading(true);
      for (let i = 0; i < inputFiles.length; i++) {
        const formData = new FormData();
        formData.append('files', inputFiles[i]);

        try {
          const response = await axios.post<{ results: APIResponse[] }>(apiUrl, formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
            signal: controller.signal,
          });

          if (requestRevision.current !== revision || controller.signal.aborted) {
            return;
          }
          if (response.data.results && response.data.results.length > 0) {
            completedResults.push(...response.data.results);
            setApiDataList([...completedResults]);
            setCurrentFileIndex(completedResults.length - 1);
          }
        } catch (err: any) {
          if (
            requestRevision.current !== revision ||
            controller.signal.aborted ||
            axios.isCancel(err)
          ) {
            return;
          }
          console.error(`Lỗi xử lý file ${inputFiles[i].name}:`, err);
          alert(`Lỗi khi tải lên file ${inputFiles[i].name}: ${err.response?.data?.detail || err.message}`);
        }
      }
      if (requestRevision.current === revision) {
        setLoading(false);
      }
    };

    void processFiles();
    return () => {
      controller.abort();
    };
  }, [inputFiles, inputRevision]);

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) {
      handleFiles(event.target.files);
      event.target.value = '';
    }
  };

  const handleDeleteCurrentFile = () => {
    setApiDataList(prev => {
      const newList = prev.filter((_, idx) => idx !== currentFileIndex);
      if (newList.length === 0) {
        setCurrentFileIndex(0);
      } else if (currentFileIndex >= newList.length) {
        setCurrentFileIndex(newList.length - 1);
      }
      return newList;
    });
  };

  const dragCounter = useRef(0);
  const [isDraggingGlobal, setIsDraggingGlobal] = useState(false);

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current += 1;
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDraggingGlobal(true);
    }
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current -= 1;
    if (dragCounter.current === 0) {
      setIsDraggingGlobal(false);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingGlobal(false);
    dragCounter.current = 0;
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFiles(e.dataTransfer.files);
    }
  };

  const sharedProps = {
    apiDataList,
    currentFileIndex,
    loading,
    selectedEvent,
    handleFiles,
    handleFileUpload,
    handleDeleteCurrentFile,
    setCurrentFileIndex,
    setSelectedEvent,
  };

  if (!isActive) {
    return null;
  }

  return (
    <div
      className="app-container"
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      style={{ height: '100%', minHeight: 0 }}
    >
      {isDraggingGlobal && (
        <div className="global-drag-overlay">
          <div className="global-drag-overlay-content">
            <h2>Kéo thả file vào đây</h2>
            <p>Hỗ trợ định dạng .sor, .msor, .trc</p>
          </div>
        </div>
      )}
      {isDesktop ? <DesktopLayout {...sharedProps} /> : <MobileLayout {...sharedProps} />}
    </div>
  );
};

export default CurrentApp;
