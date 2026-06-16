import { Mail, Pencil, Plus, Send, Trash2 } from 'lucide-react';
import { useState } from 'react';
import toast from 'react-hot-toast';
import StatusBadge from '../components/StatusBadge';

const initialTemplates = [
  { id: 'TPL-001', name: 'Payment receipt', audience: 'Paying customers', subject: 'Your EXPRESS WIFI receipt', status: 'active', body: 'Thank you {{name}}. Your payment is complete.' },
  { id: 'TPL-002', name: 'Expiry reminder', audience: 'Expiring users', subject: 'Internet package expiring soon', status: 'active', body: 'Your package expires soon. Renew to stay connected.' },
  { id: 'TPL-003', name: 'Maintenance notice', audience: 'All customers', subject: 'Scheduled maintenance window', status: 'draft', body: 'We will perform network maintenance tonight.' },
];

const blankTemplate = { id: '', name: '', audience: '', subject: '', status: 'draft', body: '' };

export default function Emails() {
  const [templates, setTemplates] = useState(initialTemplates);
  const [draft, setDraft] = useState(blankTemplate);
  const [editingId, setEditingId] = useState(null);

  const save = (event) => {
    event.preventDefault();
    const payload = { ...draft, id: draft.id || `TPL-${Date.now().toString().slice(-4)}` };
    setTemplates((current) => (editingId ? current.map((item) => (item.id === editingId ? payload : item)) : [payload, ...current]));
    setDraft(blankTemplate);
    setEditingId(null);
    toast.success('Email template saved');
  };

  const remove = (template) => {
    setTemplates((current) => current.filter((item) => item.id !== template.id));
    toast.success('Email template deleted');
  };

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
      <section className="space-y-3">
        <div>
          <h1 className="page-title">Emails</h1>
          <p className="page-subtitle">Manage invoice, receipt, expiry, and maintenance email templates.</p>
        </div>
        {templates.map((template) => (
          <article key={template.id} className="surface-card p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <Mail size={16} className="text-app-navy" />
                  <p className="text-sm font-medium text-slate-950">{template.name}</p>
                  <StatusBadge status={template.status} />
                </div>
                <p className="mt-1 text-xs text-slate-500">{template.audience}</p>
                <p className="mt-3 text-xs font-medium text-slate-700">{template.subject}</p>
              </div>
              <div className="flex gap-2">
                <button className="btn-secondary" type="button" onClick={() => toast('Test email sent')}><Send size={14} />Test</button>
                <button className="btn-secondary" type="button" onClick={() => { setDraft(template); setEditingId(template.id); }}><Pencil size={14} />Edit</button>
                <button className="btn-danger" type="button" onClick={() => remove(template)}><Trash2 size={14} />Delete</button>
              </div>
            </div>
          </article>
        ))}
      </section>

      <form className="surface-card p-4" onSubmit={save}>
        <div className="mb-4 flex items-center gap-2 border-b border-slate-200 pb-3">
          <Plus size={17} className="text-app-navy" />
          <h2 className="text-sm font-normal text-slate-950">{editingId ? 'Edit template' : 'Create template'}</h2>
        </div>
        <div className="space-y-3">
          <input className="form-input" placeholder="Template name" value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} />
          <input className="form-input" placeholder="Audience" value={draft.audience} onChange={(e) => setDraft((d) => ({ ...d, audience: e.target.value }))} />
          <input className="form-input" placeholder="Subject" value={draft.subject} onChange={(e) => setDraft((d) => ({ ...d, subject: e.target.value }))} />
          <select className="form-input" value={draft.status} onChange={(e) => setDraft((d) => ({ ...d, status: e.target.value }))}><option value="draft">Draft</option><option value="active">Active</option></select>
          <textarea className="min-h-56 w-full rounded-md border border-slate-300 px-3 py-2 text-xs outline-none focus:border-app-navy focus:ring-2 focus:ring-blue-100" placeholder="Email body" value={draft.body} onChange={(e) => setDraft((d) => ({ ...d, body: e.target.value }))} />
        </div>
        <button className="btn-primary mt-4 w-full" type="submit"><Mail size={15} />Save template</button>
      </form>
    </div>
  );
}
