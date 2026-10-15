import React, { useState, useEffect } from 'react';
import { ApiClient } from '../api';
import type { EvidenceItem } from '../types';
import { Upload, FileText, CheckCircle, AlertTriangle, FileCode } from 'lucide-react';

interface EvidenceUploadPanelProps {
  patientId: string;
  sessionId: string;
  onEvidenceUploaded?: (evidence: EvidenceItem) => void;
}

export const EvidenceUploadPanel: React.FC<EvidenceUploadPanelProps> = ({
  patientId,
  sessionId,
  onEvidenceUploaded,
}) => {
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [uploadStatus, setUploadStatus] = useState<{
    success: boolean;
    message: string;
    summary?: any;
  } | null>(null);
  const [evidenceList, setEvidenceList] = useState<EvidenceItem[]>([]);
  const [isFetchingList, setIsFetchingList] = useState<boolean>(false);

  // Load existing evidence for session on mount
  const refreshEvidenceList = async () => {
    setIsFetchingList(true);
    try {
      const res = await ApiClient.listEvidence(sessionId);
      setEvidenceList(res.evidence);
    } catch (err) {
      console.error('Failed to list evidence items:', err);
    } finally {
      setIsFetchingList(false);
    }
  };

  useEffect(() => {
    refreshEvidenceList();
  }, [sessionId]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setUploadStatus(null);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setIsUploading(true);
    setUploadStatus(null);

    try {
      const res = await ApiClient.uploadEvidence(file, patientId, sessionId);
      setUploadStatus({
        success: true,
        message: `Successfully processed ${res.file_type} evidence (${res.filename}).`,
        summary: res.summary,
      });
      setFile(null);
      await refreshEvidenceList();
      if (onEvidenceUploaded && res.evidence) {
        onEvidenceUploaded(res.evidence);
      }
    } catch (err: any) {
      setUploadStatus({
        success: false,
        message: err.message || 'Evidence upload and parsing failed.',
      });
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="card space-y-3">
      {/* Header */}
      <div className="flex justify-between items-center border-b border-slate-800 pb-2">
        <div className="flex items-center gap-2">
          <Upload className="w-4 h-4 text-sky-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Evidence Ingestion & Document Intake
          </span>
        </div>
        <span className="badge badge-blue">CSV / PDF Supported</span>
      </div>

      {/* Upload Form */}
      <div className="bg-slate-950 p-2.5 rounded border border-slate-800 space-y-2 text-xs">
        <div className="flex items-center gap-2">
          <input
            type="file"
            accept=".csv,.pdf"
            onChange={handleFileChange}
            className="flex-1 text-[11px] text-slate-400 file:mr-2 file:py-1 file:px-2.5 file:rounded file:border-0 file:text-[11px] file:bg-slate-800 file:text-slate-200 hover:file:bg-slate-700 cursor-pointer"
          />
          <button
            onClick={handleUpload}
            disabled={!file || isUploading}
            className={`btn btn-primary py-1 px-3 text-[11px] flex items-center gap-1 ${
              !file || isUploading ? 'opacity-50 cursor-not-allowed' : ''
            }`}
          >
            <Upload className="w-3 h-3" />
            <span>{isUploading ? 'Parsing...' : 'Upload Evidence'}</span>
          </button>
        </div>

        {uploadStatus && (
          <div
            className={`p-2 rounded text-xs flex items-start gap-2 ${
              uploadStatus.success
                ? 'bg-emerald-950/60 border border-emerald-800 text-emerald-200'
                : 'bg-rose-950/60 border border-rose-800 text-rose-200'
            }`}
          >
            {uploadStatus.success ? (
              <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            ) : (
              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
            )}
            <div className="space-y-1">
              <div>{uploadStatus.message}</div>
              {uploadStatus.summary && (
                <div className="text-[10px] font-mono text-slate-400 bg-slate-900/80 p-1.5 rounded">
                  {JSON.stringify(uploadStatus.summary, null, 2)}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Evidence Registry Table */}
      <div className="space-y-1.5">
        <div className="flex justify-between items-center text-[11px] text-slate-400 font-medium">
          <span>Session Evidence Registry ({evidenceList.length})</span>
          <button
            onClick={refreshEvidenceList}
            className="text-[10px] text-sky-400 hover:underline"
          >
            {isFetchingList ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>

        <div className="max-h-36 overflow-y-auto space-y-1 pr-1 text-xs divide-y divide-slate-800/40">
          {evidenceList.length === 0 ? (
            <div className="text-slate-500 py-3 text-center italic text-[11px]">
              No uploaded evidence files for this session yet. Upload a CSV or PDF above.
            </div>
          ) : (
            evidenceList.map((item) => (
              <div key={item.evidence_id} className="pt-1.5 flex items-start justify-between gap-2">
                <div className="flex items-start gap-1.5 min-w-0">
                  {item.file_type === 'PDF' ? (
                    <FileText className="w-3.5 h-3.5 text-rose-400 shrink-0 mt-0.5" />
                  ) : (
                    <FileCode className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                  )}
                  <div className="truncate">
                    <span className="font-semibold text-slate-200 text-[11px] block truncate">
                      {item.filename}
                    </span>
                    <span className="text-[10px] text-slate-500 font-mono block">
                      SHA: {item.file_hash.slice(0, 10)}... | {item.status}
                    </span>
                  </div>
                </div>

                <div className="text-right text-[10px] text-slate-400 shrink-0 font-mono">
                  {(item.file_size_bytes / 1024).toFixed(1)} KB
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

