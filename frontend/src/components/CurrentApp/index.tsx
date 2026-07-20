import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import MobileLayout from './MobileLayout';
import DesktopLayout from './DesktopLayout';
import { APIResponse } from '../../types';

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

const CurrentApp: React.FC = () => {
  const isDesktop = useMediaQuery('(min-width: 1024px)');
  const [apiDataList, setApiDataList] = useState<APIResponse[]>([]);
  const [currentFileIndex, setCurrentFileIndex] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(false);
  const [selectedEvent, setSelectedEvent] = useState<any>(null);

  const handleFiles = async (fileList: FileList) => {
    if (!fileList || fileList.length === 0) return;
    const files = Array.from(fileList);
    setLoading(true);
    setSelectedEvent(null);
    
    // Updated route to point to /current API
    const apiUrl = '/current/api/upload-otdr';
    let totalItems = apiDataList.length;

    try {
      for (let i = 0; i < files.length; i++) {
        const formData = new FormData();
        formData.append('files', files[i]);
        
        try {
          const response = await axios.post<{ results: APIResponse[] }>(apiUrl, formData, {
            headers: { 'Content-Type': 'multipart/form-data' }
          });
          
          if (response.data.results && response.data.results.length > 0) {
            const newResults = response.data.results;
            setApiDataList(prev => [...prev, ...newResults]);
            totalItems += newResults.length;
            setCurrentFileIndex(totalItems - 1);
          }
        } catch (err: any) {
          console.error(`Lỗi xử lý file ${files[i].name}:`, err);
          alert(`Lỗi khi tải lên file ${files[i].name}: ${err.response?.data?.detail || err.message}`);
        }
      }
    } finally {
      setLoading(false);
    }
  };

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

  return (
    <div
      className="app-container"
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      style={{height: '100%'}}
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
