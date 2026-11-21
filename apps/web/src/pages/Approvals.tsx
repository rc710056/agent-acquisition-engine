import React, { useEffect, useState } from 'react';
import { ShieldCheck, Check, X } from 'lucide-react';
import { api } from '../services/api';

interface ApprovalItem {
  approval_id?: string;
  id?: string;
  source_id?: string;
  format_id?: string;
  status: string;
  reason?: string;
  estimated_size_bytes?: number | null;
  created_at: string;
}

export const Approvals: React.FC = () => {
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [deciding, setDeciding] = useState<string | null>(null);

  const fetchApprovals = async () => {
    try {
      const data = await api.listApprovals();
      setApprovals(data);
    } catch (e) {
      console.error('Failed to load approvals', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchApprovals();
  }, []);

  const handleDecision = async (approvalId: string, decision: 'approved' | 'rejected') => {
    setDeciding(approvalId);
    try {
      await api.decideApproval(approvalId, decision);
      await fetchApprovals();
    } catch (e) {
      console.error('Failed to submit decision', e);
    } finally {
      setDeciding(null);
    }
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div>
        <h2 className="text-xl font-semibold text-gray-100 tracking-tight">Human-in-the-Loop Approvals</h2>
        <p className="text-xs text-gray-400 mt-1">
          Review, approve, or reject high-bandwidth, oversized, or policy-flagged acquisition requests submitted by external AI agents.
        </p>
      </div>

      {loading ? (
        <div className="p-12 text-center text-xs text-gray-500 font-mono">Loading approval queue...</div>
      ) : approvals.length === 0 ? (
        <div className="p-12 text-center rounded-xl border border-dashed border-amoled-border bg-amoled-card/20">
          <ShieldCheck className="w-8 h-8 text-gray-600 mx-auto mb-2" />
          <p className="text-xs text-gray-400">No pending approval requests.</p>
          <p className="text-[11px] text-gray-600 mt-1">
            When an agent calls request_approval for files &gt; 50 MB, requests will appear here for operator decision.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {approvals.map((appr) => {
            const approvalKey = appr.approval_id || appr.id || Math.random().toString();
            return (
              <div
                key={approvalKey}
                className="p-4 rounded-xl border border-amoled-border bg-amoled-card/60 flex items-center justify-between shadow-lg"
              >
                <div className="space-y-1">
                  <div className="flex items-center space-x-2">
                    <span className="text-xs font-semibold text-gray-200">
                      Source: {appr.source_id ? `${appr.source_id.slice(0, 12)}...` : 'Direct Source'}
                    </span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-medium ${
                      appr.status === 'approved' ? 'bg-emerald-950/40 text-emerald-400 border border-emerald-800/40' :
                      appr.status === 'rejected' ? 'bg-red-950/40 text-red-400 border border-red-800/40' :
                      'bg-amber-950/40 text-amber-400 border border-amber-800/40'
                    }`}>
                      {appr.status.toUpperCase()}
                    </span>
                  </div>
                  {appr.reason && <p className="text-xs text-gray-400 font-mono">Reason: {appr.reason}</p>}
                  <div className="flex items-center space-x-3 text-[10px] text-gray-500 font-mono">
                    {appr.format_id && <span>Format: {appr.format_id}</span>}
                    {appr.estimated_size_bytes && (
                      <span>• Size: {(appr.estimated_size_bytes / 1024 / 1024).toFixed(2)} MB</span>
                    )}
                    <span>• Requested: {new Date(appr.created_at).toLocaleTimeString()}</span>
                  </div>
                </div>

                {appr.status === 'pending' && (
                  <div className="flex items-center space-x-2">
                    <button
                      onClick={() => handleDecision(approvalKey, 'rejected')}
                      disabled={deciding === approvalKey}
                      className="px-3 py-1.5 rounded bg-amoled-input hover:bg-red-950/40 hover:text-red-400 border border-amoled-border text-xs text-gray-400 flex items-center space-x-1 transition-colors"
                    >
                      <X className="w-3.5 h-3.5" />
                      <span>Reject</span>
                    </button>
                    <button
                      onClick={() => handleDecision(approvalKey, 'approved')}
                      disabled={deciding === approvalKey}
                      className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-xs font-medium text-white flex items-center space-x-1 transition-colors shadow-sm"
                    >
                      <Check className="w-3.5 h-3.5" />
                      <span>Approve</span>
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
