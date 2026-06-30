import React, { useState, useEffect } from 'react';
import axios from 'axios';
import MobileLayout from './MobileLayout';
import DesktopLayout from './DesktopLayout';
import { APIResponse } from './types';

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

const App: React.FC = () => {
  // Coi màn hình lớn hơn 1024px là Desktop
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
    
    const apiUrl = '/api/upload-otdr';

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

  if (isDesktop) {
    return <DesktopLayout {...sharedProps} />;
  }

  return <MobileLayout {...sharedProps} />;
};

export default App;