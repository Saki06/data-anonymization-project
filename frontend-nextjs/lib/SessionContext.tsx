'use client';

import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export interface DatasetInfo {
  session_id: string;
  columns: string[];
  shape: [number, number];
  sample_data: Record<string, unknown>[];
}

interface SessionContextType {
  sessionId: string;
  datasetInfo: DatasetInfo | null;
  quasiIdentifiers: string[];
  sensitiveAttributes: string[];
  setSession: (sessionId: string, info: DatasetInfo) => void;
  setQuasiIdentifiers: (qis: string[], sens: string[]) => void;
  clearSession: () => void;
}

const SessionContext = createContext<SessionContextType | undefined>(undefined);
const LS_KEY = 'anonymization_session_v1';

type PersistedSession = {
  sessionId: string;
  datasetInfo: DatasetInfo | null;
  quasiIdentifiers: string[];
  sensitiveAttributes: string[];
};

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [sessionId, setSessionId] = useState('');
  const [datasetInfo, setDatasetInfo] = useState<DatasetInfo | null>(null);
  const [quasiIdentifiers, setQuasiIdentifiersState] = useState<string[]>([]);
  const [sensitiveAttributes, setSensitiveAttributesState] = useState<string[]>([]);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(LS_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw) as PersistedSession;
      setSessionId(parsed.sessionId || '');
      setDatasetInfo(parsed.datasetInfo || null);
      setQuasiIdentifiersState(parsed.quasiIdentifiers || []);
      setSensitiveAttributesState(parsed.sensitiveAttributes || []);
    } catch {
      // Ignore corrupt localStorage data.
    }
  }, []);

  useEffect(() => {
    const payload: PersistedSession = {
      sessionId,
      datasetInfo,
      quasiIdentifiers,
      sensitiveAttributes,
    };
    localStorage.setItem(LS_KEY, JSON.stringify(payload));
  }, [sessionId, datasetInfo, quasiIdentifiers, sensitiveAttributes]);

  const value = useMemo<SessionContextType>(
    () => ({
      sessionId,
      datasetInfo,
      quasiIdentifiers,
      sensitiveAttributes,
      setSession: (sid, info) => {
        setSessionId(sid);
        setDatasetInfo(info);
      },
      setQuasiIdentifiers: (qis, sens) => {
        setQuasiIdentifiersState(qis);
        setSensitiveAttributesState(sens);
      },
      clearSession: () => {
        setSessionId('');
        setDatasetInfo(null);
        setQuasiIdentifiersState([]);
        setSensitiveAttributesState([]);
        localStorage.removeItem(LS_KEY);
      },
    }),
    [sessionId, datasetInfo, quasiIdentifiers, sensitiveAttributes]
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextType {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error('useSession must be used within SessionProvider');
  }
  return context;
}
