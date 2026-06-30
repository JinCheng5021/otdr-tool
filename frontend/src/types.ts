import React from 'react';

export interface Trace {
  trace_name: string;
  metadata: {
    wavelength: string;
    pulse_width: string;
    index_of_refraction: number;
    number_of_data_points: number;
    total_loss: number;
    fiber_length: number;
    measurement_date: string;
    machine_type: string;
  };
  data: number[][];
  events: any[];
}

export interface APIResponse {
  status: string;
  filename: string;
  total_traces: number;
  traces: Trace[];
}

export interface SharedLayoutProps {
  apiDataList: APIResponse[];
  currentFileIndex: number;
  loading: boolean;
  selectedEvent: any;
  handleFiles: (files: FileList) => Promise<void>;
  handleFileUpload: (event: React.ChangeEvent<HTMLInputElement>) => void;
  handleDeleteCurrentFile: () => void;
  setCurrentFileIndex: React.Dispatch<React.SetStateAction<number>>;
  setSelectedEvent: React.Dispatch<React.SetStateAction<any>>;
}
