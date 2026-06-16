import { Pencil, Plus, Search, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import api from '../api/axios';

const blankTicket = {
  title: '',
  description: '',
  customer_id: '',
  status: 'open',
  priority: 'medium',
};

const statusColumns = [
  ['open', 'Open'],
  ['in-progress', 'In Progress'],
  ['resolved', 'Resolved'],
  ['closed', 'Closed'],
];

function priorityClass(priority) {
  if (priority === 'urgent') return 'bg-red-100 text-red-700';
  if (priority === 'high') return 'bg-orange-100 text-orange-700';
  if (priority === 'low') return 'bg-slate-100 text-slate-600';
  return 'bg-blue-100 text-blue-700';
}

export default function IspOperations() {
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [draft, setDraft] = useState(blankTicket);
  const [editingId, setEditingId] = useState(null);
  const [showForm, setShowForm] = useState(false);

  async function loadTickets() {
    setLoading(true);
    try {
      const { data } = await api.get('/tickets?all=1');
      setTickets(Array.isArray(data) ? data : data.results || []);
    } catch (error) {
      toast.error(error.response?.data?.message || 'Failed to load tickets');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadTickets();
  }, []);

  const filtered = useMemo(() => {
    return tickets.filter((ticket) => `${ticket.title} ${ticket.description} ${ticket.priority} ${ticket.status}`.toLowerCase().includes(query.toLowerCase()));
  }, [tickets, query]);

  const save = async (event) => {
    event.preventDefault();
    try {
      if (editingId) {
        await api.patch(`/tickets/${editingId}`, draft);
        toast.success('Ticket updated');
      } else {
        await api.post('/tickets/add', draft);
        toast.success('Ticket created');
      }
      setDraft(blankTicket);
      setEditingId(null);
      setShowForm(false);
      loadTickets();
    } catch (error) {
      toast.error(error.response?.data?.message || 'Failed to save ticket');
    }
  };

  const edit = (ticket) => {
    setDraft({
      title: ticket.title || '',
      description: ticket.description || '',
      customer_id: ticket.customer_id || '',
      status: ticket.status || 'open',
      priority: ticket.priority || 'medium',
    });
    setEditingId(ticket.id);
    setShowForm(true);
  };

  const remove = async (ticket) => {
    if (!window.confirm(`Delete ticket "${ticket.title}"?`)) return;
    try {
      await api.delete(`/tickets/${ticket.id}`);
      toast.success('Ticket deleted');
      loadTickets();
    } catch (error) {
      toast.error(error.response?.data?.message || 'Failed to delete ticket');
    }
  };

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-lg font-semibold text-slate-800">Tickets</h1>
            <p className="text-sm text-slate-500">Track customer issues, outages, billing problems, and field work.</p>
          </div>
          <button type="button" className="btn-primary" onClick={() => { setDraft(blankTicket); setEditingId(null); setShowForm(true); }}>
            <Plus size={16} />
            New ticket
          </button>
        </div>
      </section>

      {showForm && (
        <form className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" onSubmit={save}>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="block text-xs font-medium text-slate-500">
              Title
              <input className="form-input" value={draft.title} onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))} required />
            </label>
            <label className="block text-xs font-medium text-slate-500">
              Customer ID
              <input className="form-input" value={draft.customer_id} onChange={(event) => setDraft((current) => ({ ...current, customer_id: event.target.value }))} />
            </label>
            <label className="block text-xs font-medium text-slate-500">
              Status
              <select className="form-input" value={draft.status} onChange={(event) => setDraft((current) => ({ ...current, status: event.target.value }))}>
                {statusColumns.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label className="block text-xs font-medium text-slate-500">
              Priority
              <select className="form-input" value={draft.priority} onChange={(event) => setDraft((current) => ({ ...current, priority: event.target.value }))}>
                {['low', 'medium', 'high', 'urgent'].map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
          </div>
          <label className="mt-4 block text-xs font-medium text-slate-500">
            Description
            <textarea className="form-input min-h-28" value={draft.description} onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))} />
          </label>
          <div className="mt-4 flex gap-2">
            <button type="submit" className="btn-primary">{editingId ? 'Update ticket' : 'Create ticket'}</button>
            <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>Cancel</button>
          </div>
        </form>
      )}

      <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-100 p-4">
          <label className="relative block max-w-sm">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input className="form-input mt-0 pl-9" placeholder="Search tickets" value={query} onChange={(event) => setQuery(event.target.value)} />
          </label>
        </div>
        {loading ? (
          <div className="py-16 text-center text-sm text-slate-400">Loading tickets...</div>
        ) : (
          <div className="grid gap-4 p-4 xl:grid-cols-4">
            {statusColumns.map(([status, label]) => (
              <div key={status} className="rounded-lg border border-slate-100 bg-slate-50 p-3">
                <h2 className="mb-3 text-sm font-semibold text-slate-700">{label}</h2>
                <div className="space-y-3">
                  {filtered.filter((ticket) => ticket.status === status).map((ticket) => (
                    <article key={ticket.id} className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
                      <div className="flex items-start justify-between gap-2">
                        <h3 className="text-sm font-semibold text-slate-900">{ticket.title}</h3>
                        <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${priorityClass(ticket.priority)}`}>{ticket.priority}</span>
                      </div>
                      <p className="mt-2 line-clamp-3 text-xs text-slate-500">{ticket.description || 'No description'}</p>
                      <div className="mt-3 flex justify-end gap-2">
                        <button type="button" className="btn-secondary px-2 py-1 text-xs" onClick={() => edit(ticket)}><Pencil size={13} />Edit</button>
                        <button type="button" className="btn-secondary px-2 py-1 text-xs text-red-600" onClick={() => remove(ticket)}><Trash2 size={13} />Delete</button>
                      </div>
                    </article>
                  ))}
                  {filtered.filter((ticket) => ticket.status === status).length === 0 && <p className="py-8 text-center text-xs text-slate-400">No tickets</p>}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
