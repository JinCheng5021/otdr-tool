import React, { useState, useEffect, useRef } from 'react';

const NotificationDropdown: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [notifications, setNotifications] = useState<any[]>([]);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    if (isOpen) {
      fetchNotifications();
    }
  }, [isOpen]);

  const fetchNotifications = async () => {
    try {
      const res = await fetch('http://localhost:8000/trace/api/notifications');
      if (res.ok) {
        const json = await res.json();
        setNotifications(json.data || []);
      }
    } catch (e) {
      console.error('Failed to fetch notifications', e);
    }
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <button 
        onClick={() => setIsOpen(!isOpen)}
        className="w-10 h-10 rounded-full flex items-center justify-center text-on-surface hover:bg-surface-variant transition-colors relative border-2 border-industrial-navy"
      >
        <span className="material-symbols-outlined text-[20px]">notifications</span>
        <span className="absolute -top-1 -right-1 bg-red-500 text-white text-[9px] font-bold rounded-full w-4 h-4 flex items-center justify-center">
          {notifications.length > 0 ? notifications.length : '1'}
        </span>
      </button>

      {isOpen && (
        <div className="absolute top-14 right-0 w-[400px] bg-white rounded-xl shadow-2xl border border-outline-variant z-50 animate-fade-up overflow-hidden">
          <div className="flex justify-between items-center px-4 py-3 border-b border-outline-variant bg-surface-container-lowest">
            <h3 className="font-bold text-[14px] text-industrial-navy tracking-wide uppercase">THÔNG BÁO XUẤT TUYẾN</h3>
            <button className="text-[13px] font-bold text-primary hover:underline">Đọc tất cả</button>
          </div>
          
          <div className="max-h-[350px] overflow-y-auto">
            {notifications.length === 0 ? (
              <div className="p-4 text-center text-sm text-on-surface-variant">Không có thông báo nào.</div>
            ) : (
              <ul className="flex flex-col">
                {notifications.map((notif, idx) => (
                  <li key={idx} className="flex gap-4 p-4 border-b border-outline-variant hover:bg-surface-container/30 transition-colors">
                    <div className="w-12 h-12 shrink-0 bg-surface-container rounded-lg flex items-center justify-center text-industrial-navy">
                      <span className="material-symbols-outlined text-[24px]">calculate</span>
                    </div>
                    <div className="flex flex-col gap-1">
                      <p className="text-[14px] font-medium text-on-surface leading-tight">
                        {notif.message}
                      </p>
                      <span className="text-[12px] font-mono-data text-on-surface-variant">
                        {notif.export_time}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default NotificationDropdown;
