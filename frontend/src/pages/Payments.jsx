import { CheckCheck, ChevronDown, Coins, Eye, MoreVertical, Plus, Search, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import api from '../api/axios';

const blankPayment = {
  id: '',
  customer_name: '',
  phone: '',
  amount: 0,
  payment_code: '',
  status: 'success',
  paid_at: '',
  provider: 'cash',
};

function toDate(value) {
  if (!value) return null;
  if (value._seconds) return new Date(value._seconds * 1000);
  if (value.seconds) return new Date(value.seconds * 1000);
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? null : date;
}

function formatKES(value) {
  return `Ksh ${Number(value || 0).toLocaleString('en-KE', { minimumFractionDigits: 2 })}`;
}

function formatDate(value) {
  const date = toDate(value);
  if (!date) return '-';
  return `${String(date.getDate()).padStart(2, '0')}.${String(date.getMonth() + 1).padStart(2, '0')}.${date.getFullYear()} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

function sameDay(a, b) {
  return a && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

function MetricCard({ title, value, helper }) {
  return (
    <div className="rounded-md bg-[#ffb783] p-4 shadow-[0_18px_30px_rgba(15,23,42,0.12)]">
      <p className="text-xs font-semibold text-black">{title}</p>
      <div className="mt-3 flex items-center gap-2">
        <p className="text-xl font-bold text-black">{formatKES(value)}</p>
        <Eye size={14} className="text-black" />
      </div>
      <p className="mt-2 text-xs text-black">{helper}</p>
    </div>
  );
}

export default function Payments() {
  const [payments, setPayments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [tab, setTab] = useState('checked');
  const [modalOpen, setModalOpen] = useState(false);
  const [draft, setDraft] = useState(blankPayment);

  async function loadPayments() {
    setLoading(true);
    try {
      const { data } = await api.get('/payments?page_size=100');
      setPayments(Array.isArray(data) ? data : data.results || []);
    } catch (error) {
      toast.error(error.response?.data?.message || 'Failed to load payments');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadPayments();
  }, []);

  const successfulPayments = useMemo(() => payments.filter((payment) => payment.status === 'success'), [payments]);

  const rows = useMemo(() => {
    const base = tab === 'checked' ? successfulPayments : payments.filter((payment) => payment.status !== 'success');
    const needle = query.toLowerCase();
    return base.filter((payment) => `${payment.customer_name || ''} ${payment.access_username || ''} ${payment.phone || ''} ${payment.payment_code || ''} ${payment.paystack_reference || ''}`.toLowerCase().includes(needle));
  }, [payments, query, successfulPayments, tab]);

  const totals = useMemo(() => {
    const now = new Date();
    const weekStart = new Date(now);
    weekStart.setDate(now.getDate() - now.getDay());
    weekStart.setHours(0, 0, 0, 0);
    const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
    const sumSince = (start) => successfulPayments.reduce((sum, payment) => {
      const date = toDate(payment.paid_at || payment.created_at || payment.initiated_at);
      return date && date >= start ? sum + Number(payment.amount || 0) : sum;
    }, 0);
    return {
      daily: successfulPayments.reduce((sum, payment) => (sameDay(toDate(payment.paid_at || payment.created_at || payment.initiated_at), now) ? sum + Number(payment.amount || 0) : sum), 0),
      weekly: sumSince(weekStart),
      monthly: sumSince(monthStart),
    };
  }, [successfulPayments]);

  const openRecordPayment = () => {
    setDraft({ ...blankPayment, paid_at: new Date().toISOString().slice(0, 16) });
    setModalOpen(true);
  };

  const savePayment = (event) => {
    event.preventDefault();
    const payload = {
      ...draft,
      id: draft.id || `PAY-${Date.now().toString().slice(-5)}`,
      amount: Number(draft.amount || 0),
      payment_code: draft.payment_code || `MANUAL-${Date.now().toString().slice(-6)}`,
    };
    setPayments((current) => [payload, ...current]);
    setModalOpen(false);
    setDraft(blankPayment);
    toast.success('Payment recorded locally');
  };

  return (
    <div className="space-y-7">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h1 className="text-xl font-semibold text-black">Payments</h1>
          <span className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-slate-900 text-[10px]">i</span>
        </div>
        <button type="button" className="inline-flex h-9 items-center gap-2 rounded-md bg-[#ff9347] px-4 text-xs font-semibold text-black shadow-md hover:bg-[#ff842f]" onClick={openRecordPayment}>
          <Coins size={14} />
          Record Payment
        </button>
      </div>

      <section className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard title="Daily Earnings" value={totals.daily} helper="Total earnings today" />
        <MetricCard title="Weekly Earnings" value={totals.weekly} helper="Total earnings this week" />
        <MetricCard title="Monthly Earnings" value={totals.monthly} helper="Total earnings this month" />
        <MetricCard title="Mobile Money (This Month)" value={totals.monthly} helper="Excluding voucher payments" />
      </section>

      <section className="border-b border-slate-200">
        <div className="flex gap-6">
          {[
            ['checked', 'Checked payments', CheckCheck],
            ['unchecked', 'Unchecked payments', X],
          ].map(([key, label, Icon]) => (
            <button key={key} type="button" className={`inline-flex h-10 items-center gap-2 border-b-2 text-xs font-medium ${tab === key ? 'border-[#fa8200] text-[#c95f00]' : 'border-transparent text-slate-500'}`} onClick={() => setTab(key)}>
              <Icon size={15} />
              {label}
            </button>
          ))}
        </div>
      </section>

      <section className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <div className="flex justify-end border-b border-slate-200 p-3">
          <label className="relative block w-full max-w-xs">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input className="h-9 w-full rounded-md border border-slate-200 pl-9 pr-3 text-xs outline-none focus:border-[#fa8200] focus:ring-2 focus:ring-orange-100" placeholder="Search" value={query} onChange={(event) => setQuery(event.target.value)} />
          </label>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-[980px] w-full">
            <thead className="bg-slate-50 text-left text-xs font-semibold text-black">
              <tr>
                <th className="w-12 px-5 py-4"><input type="checkbox" className="h-4 w-4 rounded border-slate-300" /></th>
                {['User', 'Phone', 'Receipt No.', 'Amount', 'Checked', 'Paid At', 'Disbursement'].map((heading) => (
                  <th key={heading} className="px-5 py-4">
                    <span className="inline-flex items-center gap-1">{heading}<ChevronDown size={15} className="text-slate-400" /></span>
                  </th>
                ))}
                <th className="px-5 py-4" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 text-xs text-black">
              {loading ? (
                <tr><td className="px-5 py-10 text-center text-slate-500" colSpan="9">Loading payments...</td></tr>
              ) : rows.length === 0 ? (
                <tr><td className="px-5 py-10 text-center text-slate-500" colSpan="9">No payments found.</td></tr>
              ) : rows.map((payment) => (
                <tr key={payment.id}>
                  <td className="px-5 py-4"><input type="checkbox" className="h-4 w-4 rounded border-slate-300" /></td>
                  <td className="px-5 py-4 font-bold text-[#b95600]">{payment.customer_name || payment.access_username || '-'}</td>
                  <td className="px-5 py-4">{payment.phone || '-'}</td>
                  <td className="px-5 py-4">{payment.payment_code || payment.paystack_reference || '-'}</td>
                  <td className="px-5 py-4">{formatKES(payment.amount)}</td>
                  <td className="px-5 py-4"><span className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-[10px] text-emerald-700">{payment.status === 'success' ? 'Yes' : 'No'}</span></td>
                  <td className="px-5 py-4">{formatDate(payment.paid_at || payment.created_at || payment.initiated_at)}</td>
                  <td className="px-5 py-4"><span className="rounded-md border border-orange-200 bg-orange-50 px-2 py-1 text-[10px] text-[#c95f00]">{payment.provider === 'voucher' ? 'Voucher' : 'Direct'}</span></td>
                  <td className="px-5 py-4 text-right text-[#fa8200]"><MoreVertical size={16} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4">
          <form className="w-full max-w-lg rounded-lg bg-white p-5 shadow-xl" onSubmit={savePayment}>
            <h2 className="text-base font-semibold text-black">Record Payment</h2>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <label className="text-xs font-semibold text-slate-600">User<input className="form-input" value={draft.customer_name} onChange={(event) => setDraft((current) => ({ ...current, customer_name: event.target.value }))} required /></label>
              <label className="text-xs font-semibold text-slate-600">Phone<input className="form-input" value={draft.phone} onChange={(event) => setDraft((current) => ({ ...current, phone: event.target.value }))} /></label>
              <label className="text-xs font-semibold text-slate-600">Receipt No.<input className="form-input" value={draft.payment_code} onChange={(event) => setDraft((current) => ({ ...current, payment_code: event.target.value }))} /></label>
              <label className="text-xs font-semibold text-slate-600">Amount<input className="form-input" type="number" value={draft.amount} onChange={(event) => setDraft((current) => ({ ...current, amount: event.target.value }))} required /></label>
              <label className="text-xs font-semibold text-slate-600">Paid At<input className="form-input" type="datetime-local" value={draft.paid_at} onChange={(event) => setDraft((current) => ({ ...current, paid_at: event.target.value }))} /></label>
              <label className="text-xs font-semibold text-slate-600">Status<select className="form-input" value={draft.status} onChange={(event) => setDraft((current) => ({ ...current, status: event.target.value }))}><option value="success">Checked</option><option value="pending">Unchecked</option><option value="failed">Failed</option></select></label>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" className="btn-secondary" onClick={() => setModalOpen(false)}>Cancel</button>
              <button type="submit" className="inline-flex h-8 items-center gap-2 rounded-md bg-[#ff9347] px-4 text-xs font-semibold text-black">
                <Plus size={14} />
                Save Payment
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
