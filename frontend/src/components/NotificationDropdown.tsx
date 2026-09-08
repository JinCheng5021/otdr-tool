import React, { useCallback, useState, useEffect, useRef } from 'react';

interface ExportNotification {
  id: number;
  message: string;
  export_time: string;
}

const LAST_READ_STORAGE_KEY = 'otdr_last_read_id';
const READ_IDS_STORAGE_KEY = 'otdr_read_notification_ids';

const readLastReadId = (): number => {
  if (typeof window === 'undefined') return 0;
  try {
    const storedValue = Number.parseInt(
      window.localStorage.getItem(LAST_READ_STORAGE_KEY) || '0',
      10,
    );
    return Number.isFinite(storedValue) && storedValue > 0 ? storedValue : 0;
  } catch {
    return 0;
  }
};

const notificationId = (notification: ExportNotification): number => {
  const parsedId = Number(notification.id);
  return Number.isFinite(parsedId) ? parsedId : 0;
};

const readNotificationIds = (): Set<number> => {
  if (typeof window === 'undefined') return new Set<number>();
  try {
    const storedValue = JSON.parse(
      window.localStorage.getItem(READ_IDS_STORAGE_KEY) || '[]',
    );
    if (!Array.isArray(storedValue)) return new Set<number>();
    return new Set(
      storedValue
        .map((value) => Number(value))
        .filter((value) => Number.isFinite(value) && value > 0),
    );
  } catch {
    return new Set<number>();
  }
};

const NotificationDropdown: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [notifications, setNotifications] = useState<ExportNotification[]>([]);
  const [lastReadId, setLastReadId] = useState(readLastReadId);
  const [readIds, setReadIds] = useState<Set<number>>(readNotificationIds);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const fetchNotifications = useCallback(async (): Promise<ExportNotification[]> => {
    try {
      const res = await fetch('/trace/api/notifications');
      if (res.ok) {
        const json = await res.json();
        const data = Array.isArray(json.data)
          ? json.data as ExportNotification[]
          : [];
        setNotifications(data);
        return data;
      }
    } catch (e) {
      console.error('Failed to fetch notifications', e);
    }
    return [];
  }, []);

  const markAllNotificationsRead = useCallback((items: ExportNotification[]) => {
    const newestId = items.reduce(
      (maximumId, notification) => Math.max(maximumId, notificationId(notification)),
      0,
    );
    if (newestId > 0) {
      setLastReadId((previousId) => Math.max(previousId, newestId));
      setReadIds(new Set<number>());
    }
  }, []);

  const markNotificationRead = useCallback((notification: ExportNotification) => {
    const id = notificationId(notification);
    if (id <= 0) return;
    setReadIds((previousIds) => {
      const nextIds = new Set(previousIds);
      nextIds.add(id);
      return nextIds;
    });
  }, []);

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
    void fetchNotifications();
  }, [fetchNotifications]);

  useEffect(() => {
    try {
      window.localStorage.setItem(LAST_READ_STORAGE_KEY, String(lastReadId));
    } catch {
      // Notification state still works for the current page when storage is unavailable.
    }
  }, [lastReadId]);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        READ_IDS_STORAGE_KEY,
        JSON.stringify(Array.from(readIds)),
      );
    } catch {
      // Notification state still works for the current page when storage is unavailable.
    }
  }, [readIds]);

  const unreadNotifications = notifications.filter((notification) => {
    const id = notificationId(notification);
    return id > lastReadId && !readIds.has(id);
  });
  const unreadCount = unreadNotifications.length;

  const handleToggle = () => {
    const shouldOpen = !isOpen;
    setIsOpen(shouldOpen);
    if (shouldOpen) {
      void fetchNotifications();
    }
  };

  const handleMarkAllRead = (event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    markAllNotificationsRead(notifications);
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <button 
        onClick={handleToggle}
        aria-label="Thông báo"
        className="w-10 h-10 rounded-full flex items-center justify-center text-on-surface hover:bg-surface-variant transition-colors relative border-2 border-industrial-navy"
      >
        <span className="material-symbols-outlined text-[20px]">notifications</span>
        {unreadCount > 0 && (
          <span
            data-testid="notification-badge"
            className="absolute -top-1 -right-1 bg-red-500 text-white text-[9px] font-bold rounded-full w-4 h-4 flex items-center justify-center"
          >
            {unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute top-14 right-0 w-[400px] bg-white rounded-xl shadow-2xl border border-outline-variant z-50 animate-fade-up overflow-hidden">
          <div className="flex justify-between items-center px-4 py-3 border-b border-outline-variant bg-surface-container-lowest">
            <h3 className="font-bold text-[14px] text-industrial-navy tracking-wide uppercase">THÔNG BÁO XUẤT TUYẾN</h3>
            <button
              onClick={handleMarkAllRead}
              className="text-[13px] font-bold text-primary hover:underline"
            >
              Đọc tất cả
            </button>
          </div>
          
          <div className="max-h-[350px] overflow-y-auto">
            {unreadNotifications.length === 0 ? (
              <div className="p-4 text-center text-sm text-on-surface-variant">Không có thông báo chưa đọc.</div>
            ) : (
              <ul className="flex flex-col">
                {unreadNotifications.map((notif) => (
                  <li key={notif.id} className="border-b border-outline-variant">
                    <button
                      type="button"
                      onClick={() => markNotificationRead(notif)}
                      aria-label={`Đánh dấu đã đọc: ${notif.message}`}
                      className="w-full flex gap-4 p-4 text-left hover:bg-surface-container/30 transition-colors"
                    >
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
                    </button>
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
