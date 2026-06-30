import {
  AlertTriangle,
  ArrowRight,
  CalendarDays,
  CreditCard,
  DollarSign,
  FileText,
  MoreVertical,
  RefreshCw,
  TrendingUp,
  UserPlus,
  Users,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { Link } from 'react-router-dom';
import adminApi from '../../api/adminAxios';
import { adminPath } from '../../config/adminPaths';

function formatKES(value) {
  return `KES ${Number(value || 0).toLocaleString()}`;
}

function formatDate(value) {
  return value ? new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '-';
}

function statusClass(status) {
  const normalized = String(status || '').toLowerCase();
  if (normalized === 'active') return 'bg-emerald-100 text-emerald-700';
  if (normalized === 'trial' || normalized === 'pending_setup' || normalized === 'pending') return 'bg-sky-100 text-sky-700';
  if (normalized === 'past due' || normalized === 'expired' || normalized === 'suspended') return 'bg-red-100 text-red-700';
  return 'bg-slate-100 text-slate-600';
}

function MetricCard({ label, value, trend, icon: Icon, tone = 'blue' }) {
  const tones = {
    blue: 'bg-blue-50 text-[#0d95f2]',
    cyan: 'bg-cyan-50 text-[#06a9c9]',
    green: 'bg-emerald-50 text-emerald-600',
    red: 'bg-red-50 text-red-500',
  };

  return (
    <section className="rounded-xl border border-slate-100 bg-white p-6 shadow-[0_12px_34px_rgba(15,34,64,0.06)]">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[13px] font-bold text-[#102347]">{label}</p>
          <p className="mt-2 text-2xl font-extrabold tracking-tight text-[#0d95f2]">{value}</p>
        </div>
        <div className={`flex h-16 w-16 shrink-0 items-center justify-center rounded-full ${tones[tone]}`}>
          <Icon size={30} strokeWidth={2} />
        </div>
      </div>
      <div className="mt-3 text-[12px] font-semibold">
        <span className={trend >= 0 ? 'text-[#0d95f2]' : 'text-red-500'}>{trend >= 0 ? '+' : ''}{trend.toFixed(1)}%</span>
        <span className="ml-2 text-slate-500">vs last period</span>
      </div>
    </section>
  );
}

function RevenueChart({ data }) {
  const points = useMemo(() => {
    const max = Math.max(...data.map((item) => Number(item.amount) || 0), 1);
    return data.map((item, index) => {
      const x = data.length <= 1 ? 0 : (index / (data.length - 1)) * 600;
      const y = 220 - ((Number(item.amount) || 0) / max) * 180;
      return { x, y, ...item };
    });
  }, [data]);

  const line = points.map((point) => `${point.x},${point.y}`).join(' ');
  const area = points.length ? `0,240 ${line} 600,240` : '';

  return (
    <section className="rounded-xl border border-slate-100 bg-white p-6 shadow-[0_12px_34px_rgba(15,34,64,0.06)] xl:col-span-2">
      <div className="mb-5 flex items-center justify-between">
        <h2 className="text-[15px] font-extrabold text-[#102347]">Revenue Overview</h2>
        <select className="h-9 rounded-md border border-slate-200 bg-white px-3 text-[12px] font-semibold text-[#102347] outline-none">
          <option>Daily</option>
        </select>
      </div>

      <div className="relative h-[245px]">
        <div className="absolute inset-0 grid grid-rows-5 text-[11px] font-semibold text-slate-400">
          {['KES 300K', 'KES 250K', 'KES 200K', 'KES 150K', 'KES 0'].map((label) => (
            <div key={label} className="flex items-start gap-3 border-t border-dashed border-slate-200">
              <span className="w-16 -translate-y-2">{label}</span>
            </div>
          ))}
        </div>
        <svg className="absolute left-16 top-0 h-[230px] w-[calc(100%-4rem)] overflow-visible" viewBox="0 0 600 240" preserveAspectRatio="none">
          <defs>
            <linearGradient id="revenueFill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#159fff" stopOpacity="0.28" />
              <stop offset="100%" stopColor="#159fff" stopOpacity="0.03" />
            </linearGradient>
          </defs>
          {points.length > 0 && <polygon points={area} fill="url(#revenueFill)" />}
          {points.length > 0 && <polyline points={line} fill="none" stroke="#118cf0" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />}
          {points.map((point) => (
            <circle key={`${point.date}-${point.x}`} cx={point.x} cy={point.y} r="4" fill="#118cf0" />
          ))}
        </svg>
      </div>

      <div className="ml-16 mt-2 grid grid-cols-5 text-[11px] font-semibold text-slate-500">
        {['May 1', 'May 6', 'May 11', 'May 16', 'May 21'].map((label) => <span key={label}>{label}</span>)}
      </div>
    </section>
  );
}

function SubscriptionOverview({ stats }) {
  const active = Number(stats?.activeTenants || 0);
  const trial = Number(stats?.pendingTenants || 0);
  const pastDue = Number(stats?.expiredCount || 0);
  const cancelled = Number(stats?.suspendedTenants || 0);
  const total = Math.max(active + trial + pastDue + cancelled, 1);
  const activePct = (active / total) * 100;
  const trialPct = activePct + (trial / total) * 100;
  const pastDuePct = trialPct + (pastDue / total) * 100;
  const donut = `conic-gradient(#118cf0 0 ${activePct}%, #14b8d8 ${activePct}% ${trialPct}%, #f6b23d ${trialPct}% ${pastDuePct}%, #ff4f7b ${pastDuePct}% 100%)`;
  const rows = [
    ['Active', active, '#118cf0'],
    ['Trial', trial, '#14b8d8'],
    ['Past Due', pastDue, '#f6b23d'],
    ['Canceled', cancelled, '#ff4f7b'],
  ];

  return (
    <section className="rounded-xl border border-slate-100 bg-white p-6 shadow-[0_12px_34px_rgba(15,34,64,0.06)]">
      <h2 className="text-[15px] font-extrabold text-[#102347]">Subscription Overview</h2>
      <div className="mt-7 flex flex-col items-center gap-7 sm:flex-row">
        <div className="relative h-40 w-40 rounded-full" style={{ background: donut }}>
          <div className="absolute inset-5 flex flex-col items-center justify-center rounded-full bg-white">
            <span className="text-3xl font-extrabold text-[#102347]">{total === 1 && active + trial + pastDue + cancelled === 0 ? 0 : total}</span>
            <span className="text-[12px] font-semibold text-slate-400">Total</span>
          </div>
        </div>
        <div className="flex-1 space-y-4">
          {rows.map(([label, value, color]) => (
            <div key={label} className="flex items-center justify-between gap-4 text-[12px]">
              <span className="flex items-center gap-3 font-bold text-[#102347]">
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
                {label}
              </span>
              <span className="font-semibold text-slate-500">{value} ({total ? ((value / total) * 100).toFixed(1) : '0.0'}%)</span>
            </div>
          ))}
        </div>
      </div>
      <Link to={adminPath('subscriptions')} className="mt-6 flex h-10 items-center justify-center rounded-md border border-[#118cf0] text-[12px] font-bold text-[#118cf0] hover:bg-blue-50">
        View All Subscriptions
      </Link>
    </section>
  );
}

function ActivityIcon({ action }) {
  const text = String(action || '').toLowerCase();
  if (text.includes('payment')) return [DollarSign, 'bg-[#118cf0]'];
  if (text.includes('tenant') || text.includes('user')) return [UserPlus, 'bg-emerald-500'];
  if (text.includes('invoice') || text.includes('subscription')) return [FileText, 'bg-amber-400'];
  return [AlertTriangle, 'bg-red-500'];
}

export default function AdminDashboard() {
  const [stats, setStats] = useState(null);
  const [chart, setChart] = useState([]);
  const [tenants, setTenants] = useState([]);
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    try {
      const [statsRes, chartRes, tenantsRes, auditRes] = await Promise.all([
        adminApi.get('/admin/system/stats'),
        adminApi.get('/admin/subscriptions/revenue-chart?days=31'),
        adminApi.get('/admin/tenants'),
        adminApi.get('/admin/tenants/audit/logs'),
      ]);
      setStats(statsRes.data);
      setChart(Array.isArray(chartRes.data) ? chartRes.data : []);
      setTenants(Array.isArray(tenantsRes.data) ? tenantsRes.data : []);
      setActivities(Array.isArray(auditRes.data) ? auditRes.data.slice(0, 4) : []);
    } catch (error) {
      toast.error(error.response?.data?.error || 'Failed to load admin dashboard');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const timer = setInterval(load, 60000);
    return () => clearInterval(timer);
  }, []);

  const trend = useMemo(() => {
    if (chart.length < 2) return 0;
    const first = Number(chart[0]?.amount || 0);
    const last = Number(chart[chart.length - 1]?.amount || 0);
    return first ? ((last - first) / first) * 100 : 0;
  }, [chart]);

  const recentTenants = useMemo(() => {
    return [...tenants]
      .sort((a, b) => new Date(b.created_at || b.updated_at || 0) - new Date(a.created_at || a.updated_at || 0))
      .slice(0, 5);
  }, [tenants]);

  if (loading) {
    return <p className="text-sm font-medium text-slate-600">Loading admin dashboard...</p>;
  }

  return (
    <div className="space-y-5">
      <div className="flex justify-end">
        <button type="button" className="inline-flex h-10 items-center gap-2 rounded-md border border-slate-200 bg-white px-4 text-[12px] font-bold text-[#102347] shadow-sm" onClick={load}>
          <CalendarDays size={16} />
          May 1 - May 31, 2024
          <RefreshCw size={14} />
        </button>
      </div>

      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Total Revenue" value={formatKES(stats?.monthlyRevenue)} trend={trend} icon={TrendingUp} />
        <MetricCard label="Active Tenants" value={Number(stats?.activeTenants || 0).toLocaleString()} trend={12.5} icon={Users} tone="cyan" />
        <MetricCard label="MRR" value={formatKES(stats?.monthlyRevenue)} trend={15.3} icon={DollarSign} />
        <MetricCard label="Overdue Invoices" value={Number(stats?.expiredCount || 0).toLocaleString()} trend={Number(stats?.expiredCount || 0) ? -27.8 : 0} icon={FileText} tone="red" />
      </div>

      <div className="grid gap-5 xl:grid-cols-3">
        <RevenueChart data={chart} />
        <SubscriptionOverview stats={stats} />
      </div>

      <div className="grid gap-5 xl:grid-cols-[2fr_1fr]">
        <section className="overflow-hidden rounded-xl border border-slate-100 bg-white shadow-[0_12px_34px_rgba(15,34,64,0.06)]">
          <div className="border-b border-slate-100 px-6 py-4">
            <h2 className="text-[15px] font-extrabold text-[#102347]">Recent Tenants</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-[720px] w-full text-left text-[12px]">
              <thead className="text-[#102347]">
                <tr>
                  {['Tenant Name', 'Domain', 'Plan', 'Status', 'MRR', 'Joined On', 'Actions'].map((heading) => (
                    <th key={heading} className="px-6 py-4 font-extrabold">{heading}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {recentTenants.length === 0 ? (
                  <tr><td className="px-6 py-6 text-slate-500" colSpan="7">No tenants found.</td></tr>
                ) : recentTenants.map((tenant) => (
                  <tr key={tenant.id} className="text-slate-600">
                    <td className="px-6 py-4 font-bold text-[#102347]">{tenant.business_name || tenant.owner_name || '-'}</td>
                    <td className="px-6 py-4">{tenant.domain || tenant.email || '-'}</td>
                    <td className="px-6 py-4">{tenant.subscription?.plan || 'basic'}</td>
                    <td className="px-6 py-4">
                      <span className={`rounded-md px-3 py-1 text-[11px] font-bold ${statusClass(tenant.status)}`}>{tenant.status || 'active'}</span>
                    </td>
                    <td className="px-6 py-4">{formatKES(tenant.subscription?.amount)}</td>
                    <td className="px-6 py-4">{formatDate(tenant.created_at || tenant.updated_at)}</td>
                    <td className="px-6 py-4"><MoreVertical size={17} className="text-[#102347]" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Link to={adminPath('tenants')} className="flex items-center gap-3 px-6 py-5 text-[12px] font-extrabold text-[#118cf0]">
            View all tenants <ArrowRight size={15} />
          </Link>
        </section>

        <section className="rounded-xl border border-slate-100 bg-white shadow-[0_12px_34px_rgba(15,34,64,0.06)]">
          <div className="border-b border-slate-100 px-6 py-4">
            <h2 className="text-[15px] font-extrabold text-[#102347]">Recent Activities</h2>
          </div>
          <div className="divide-y divide-slate-100">
            {activities.length === 0 ? (
              <p className="px-6 py-6 text-[12px] text-slate-500">No recent activity.</p>
            ) : activities.map((activity) => {
              const [Icon, bg] = ActivityIcon({ action: activity.action });
              return (
                <div key={activity.id} className="flex gap-4 px-6 py-4">
                  <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-white ${bg}`}>
                    <Icon size={18} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[12px] font-extrabold text-[#102347]">{String(activity.action || 'Activity').replaceAll('_', ' ')}</p>
                    <p className="truncate text-[11px] font-semibold text-slate-400">{activity.admin_email || activity.target_type || '-'}</p>
                  </div>
                  <span className="whitespace-nowrap text-[11px] font-semibold text-slate-400">{activity.timestamp ? formatDate(activity.timestamp) : '-'}</span>
                </div>
              );
            })}
          </div>
          <Link to={adminPath('audit')} className="flex items-center gap-3 px-6 py-5 text-[12px] font-extrabold text-[#118cf0]">
            View all activities <ArrowRight size={15} />
          </Link>
        </section>
      </div>
    </div>
  );
}
