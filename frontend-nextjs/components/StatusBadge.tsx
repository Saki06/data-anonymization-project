'use client';

interface StatusProps {
  status: 'connected' | 'disconnected' | 'info' | 'warning' | 'checking';
  message: string;
}

const classMap: Record<string, string> = {
  connected:    'status-connected',
  disconnected: 'status-disconnected',
  info:         'status-info',
  warning:      'status-warning',
  checking:     'status-info',
};

export default function StatusBadge({ status, message }: StatusProps) {
  return <div className={`my-4 ${classMap[status] ?? 'status-info'}`}>{message}</div>;
}
