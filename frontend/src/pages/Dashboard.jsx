import { AlertTriangle, CreditCard, Filter, MessageSquare, Smartphone, Users } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import api from '../api/axios';

const ORANGE = '#d96f00';
const ORANGE_SOFT = '#ffb17a';
const PANEL = '#222326';
const PANEL_ALT = '#252629';
const GRID = '#3b3c42';

const paymentSeries = [
  ['Jan', 23000],
  ['Feb', 18000],
  ['Mar', 21000],
  ['Apr', 14000],
  ['May', 14000],
  ['Jun', 200],
  ['Jul', 100],
  ['Aug', 100],
  ['Sep', 80],
  ['Oct', 50],
  ['Nov', 0],
  ['Dec', 0],
];

const activeUsersSeries = [
  ['Mon', 36, 0],
  ['Tue', 19, 0],
  ['Wed', 5, 0],
  ['Thu', 2, 0],
  ['Fri', 1, 0],
];

const retentionSeries = [
  ['Jan 2026', 130, 70, 38, 60],
  ['Feb 2026', 138, 68, 37, 62],
  ['Mar 2026', 72, 68, 39, 62],
  ['Apr 2026', 66, 67, 34, 71],
  ['May 2026', 50, 63, 43, 78],
  ['Jun 2026', 10, 28, 75, 20],
];

const dataUsageSeries = [
  ['27 May', 62],
  ['28 May', 38],
  ['29 May', 49],
  ['30 May', 50],
  ['31 May', 75],
  ['01 Jun', 45],
  ['02 Jun', 11],
  ['03 Jun', 0],
];

const packageUtilization = [
  ['Free trial', 8, '#fff4ea'],
  ['Unlimited for 12 hours', 26, ORANGE],
  ['Unlimited for 24 hours', 34, '#ffa64d'],
  ['Unlimited for 6 hours', 20, '#ffd7bd'],
  ['Unlimited for 2 hours', 12, '#f4c099'],
];

const forecastSeries = [
  ['Dec 2025', 19000],
  ['Jan 2026', 16500],
  ['Feb 2026', 18000],
  ['Mar 2026', 13000],
  ['Apr 2026', 13200],
  ['May 2026', 8200],
  ['Jun 2026', 500],
];

const smsSeries = [
  ['Thu', 70],
  ['Fri', 190],
  ['Sat', 190],
  ['Sun', 170],
  ['Mon', 190],
  ['Tue', 40],
  ['Wed', 0],
];

const networkDataSeries = [
  ['Mon', 42],
  ['Tue', 10],
  ['Wed', 0],
];

const mostActiveUsers = [
  ['EXP287', '109.05GB', '0193400641'],
  ['EXP66', '236.8GB', '0737216543'],
  ['EXP123', '23.95GB', '0714713248'],
  ['EXP703', '4.49GB', '0711522812'],
  ['EXP768', '2.43GB', '0106503277'],
  ['EXP575', '101GB', '0721672240'],
];

const packagePerformance = [
  ['UNLIMITED FOR 6 HOURS', 'KSH 20.00', 100, 'KSH 100.00', '0.05 GB', 'KSH 1.00'],
  ['UNLIMITED FOR 2 HOURS', 'KSH 10.00', 45, 'KSH 290.00', '0.53 GB', 'KSH 6.49'],
  ['UNLIMITED FOR 12 HOURS', 'KSH 25.00', 43, 'KSH 85.00', '0.27 GB', 'KSH 1.98'],
  ['free trial', 'KSH 0.00', 37, 'KSH 0.00', '0.00 GB', 'KSH 0.00'],
  ['UNLIMITED FOR 24 HOURS', 'KSH 40.00', 8, 'KSH 75.00', '11.9 GB', 'KSH 9.38'],
  ['UNLIMITED FOR 15 HOURS', 'KSH 30.00', 1, 'KSH 30.00', '0.33 GB', 'KSH 30.00'],
  ['UNLIMITED 2 WEEKS', 'KSH 250.00', 0, 'KSH 0.00', '0 GB', 'KSH 0.00'],
  ['UNLIMITED FOR 1 WEEK', 'KSH 200.00', 0, 'KSH 0.00', '0 GB', 'KSH 0.00'],
];

function maxValue(data, index = 1) {
  return Math.max(...data.map((item) => Number(item[index]) || 0), 1);
}

function points(data, index, width = 320, height = 170, pad = 18) {
  const max = maxValue(data, index);
  return data.map((item, i) => {
    const x = pad + (i * (width - pad * 2)) / Math.max(data.length - 1, 1);
    const y = height - pad - ((Number(item[index]) || 0) / max) * (height - pad * 2);
    return `${x},${y}`;
  }).join(' ');
}

function readDarkMode() {
  try {
    const settings = JSON.parse(localStorage.getItem('tenant_settings') || '{}');
    const mode = settings.themeMode || (settings.darkMode ? 'dark' : 'light');
    if (mode === 'system') {
      return window.matchMedia('(prefers-color-scheme: dark)').matches;
    }
    return mode === 'dark';
  } catch {
    return false;
  }
}

function ChartCard({ title, subtitle, children, tall = false, darkMode = false }) {
  return (
    <section
      className={`rounded-lg border ${darkMode ? 'border-[#33343a] text-white' : 'border-slate-200 text-slate-950'} ${tall ? 'min-h-[360px]' : 'min-h-[318px]'}`}
      style={{ backgroundColor: darkMode ? PANEL : '#ffffff' }}
    >
      <div className={`flex items-start justify-between gap-3 border-b px-4 py-3 ${darkMode ? 'border-[#36373d]' : 'border-slate-200'}`}>
        <div>
          <h2 className={`text-sm font-semibold ${darkMode ? 'text-white' : 'text-slate-950'}`}>{title}</h2>
          <p className={`mt-1 text-[11px] ${darkMode ? 'text-[#a9aec3]' : 'text-slate-500'}`}>{subtitle}</p>
        </div>
        <button type="button" className={`h-8 rounded-md border px-3 text-[11px] font-semibold ${darkMode ? 'border-[#3a3b40] bg-[#292a2e] text-white' : 'border-slate-200 bg-slate-50 text-slate-700'}`}>This week</button>
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

function BarChart({ data, valueIndex = 1, height = 190 }) {
  const max = maxValue(data, valueIndex);
  return (
    <div className="flex items-end gap-3" style={{ height }}>
      {data.map((item) => (
        <div key={item[0]} className="flex flex-1 flex-col items-center gap-2">
          <div
            className="w-full max-w-[26px] rounded-t-sm"
            style={{ height: `${Math.max(((Number(item[valueIndex]) || 0) / max) * (height - 28), item[valueIndex] ? 5 : 1)}px`, background: ORANGE }}
          />
          <span className="text-[10px] text-[#9da3b8]">{item[0]}</span>
        </div>
      ))}
    </div>
  );
}

function LineChart({ data, indexes = [1], colors = [ORANGE], height = 190 }) {
  return (
    <svg viewBox="0 0 320 190" className="h-full w-full" style={{ minHeight: height }}>
      {[0, 1, 2, 3].map((line) => <line key={line} x1="18" x2="304" y1={24 + line * 42} y2={24 + line * 42} stroke={GRID} strokeWidth="1" />)}
      {indexes.map((index, lineIndex) => (
        <polyline key={index} fill="none" stroke={colors[lineIndex]} strokeWidth="3" points={points(data, index)} />
      ))}
      {indexes.map((index, lineIndex) => points(data, index).split(' ').map((point) => {
        const [cx, cy] = point.split(',');
        return <circle key={`${index}-${point}`} cx={cx} cy={cy} r="3.5" fill={colors[lineIndex]} stroke="#fff" strokeWidth="1" />;
      }))}
      {data.map((item, index) => (
        <text key={item[0]} x={18 + (index * 286) / Math.max(data.length - 1, 1)} y="184" textAnchor="middle" fill="#9da3b8" fontSize="9">{item[0].split(' ')[0]}</text>
      ))}
    </svg>
  );
}

function AreaChart({ data }) {
  const line = points(data, 1);
  return (
    <svg viewBox="0 0 320 190" className="h-[190px] w-full">
      {[0, 1, 2, 3].map((lineIndex) => <line key={lineIndex} x1="18" x2="304" y1={24 + lineIndex * 42} y2={24 + lineIndex * 42} stroke={GRID} strokeWidth="1" />)}
      <polygon points={`18,172 ${line} 304,172`} fill={ORANGE} opacity="0.95" />
      <polyline fill="none" stroke={ORANGE_SOFT} strokeWidth="2" points={line} />
      {data.map((item, index) => <text key={item[0]} x={18 + (index * 286) / Math.max(data.length - 1, 1)} y="184" textAnchor="middle" fill="#9da3b8" fontSize="9">{item[0]}</text>)}
    </svg>
  );
}

function DonutChart({ data }) {
  const total = data.reduce((sum, item) => sum + item[1], 0);
  if (!total) {
    return <div className="py-16 text-center text-xs text-slate-400">No package usage yet.</div>;
  }
  let offset = 25;
  return (
    <div className="flex flex-col items-center gap-4">
      <svg viewBox="0 0 120 120" className="h-44 w-44 -rotate-90">
        {data.map(([label, value, color]) => {
          const dash = (value / total) * 100;
          const circle = <circle key={label} cx="60" cy="60" r="38" fill="none" stroke={color} strokeWidth="22" strokeDasharray={`${dash} ${100 - dash}`} strokeDashoffset={-offset} pathLength="100" />;
          offset += dash;
          return circle;
        })}
        <circle cx="60" cy="60" r="25" fill={PANEL} />
      </svg>
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[10px] text-[#d7d9e3]">
        {data.map(([label, , color]) => <span key={label} className="flex items-center gap-2"><i className="h-2 w-2 rounded-sm" style={{ background: color }} />{label}</span>)}
      </div>
    </div>
  );
}

function TopStat({ icon: Icon, label, value, helper }) {
  return (
    <div className="rounded-md bg-[#ffb17a] px-4 py-3 text-[#261001]">
      <div className="flex items-center gap-2 text-[11px] font-semibold"><Icon size={14} />{label}</div>
      <p className="mt-2 text-xl font-bold">{value}</p>
      <p className="mt-1 text-[10px] font-semibold opacity-75">{helper}</p>
    </div>
  );
}

export default function Dashboard() {
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [darkMode, setDarkMode] = useState(() => readDarkMode());

  useEffect(() => {
    setDarkMode(readDarkMode());
    let mounted = true;
    async function load() {
      try {
        const { data } = await api.get('/dashboard/stats');
        if (mounted) {
          setDashboard(data);
        }
      } catch (error) {
        toast.error(error.response?.data?.message || 'Failed to load dashboard');
      } finally {
        if (mounted) setLoading(false);
      }
    }
    load();
    return () => { mounted = false; };
  }, []);

  const stats = useMemo(() => {
    const summary = dashboard?.summary || {};
    return {
      amountThisMonth: Number(summary.revenue_this_month || 0),
      smsBalance: Number(summary.sms_balance || 0),
      totalClients: Number(summary.total_customers || 0),
      activeClients: Number(summary.active_customers || 0),
    };
  }, [dashboard]);

  const chartData = {
    payments: dashboard?.payments_chart?.length ? dashboard.payments_chart : paymentSeries,
    activeUsers: dashboard?.active_users_chart?.length ? dashboard.active_users_chart : activeUsersSeries,
    retention: dashboard?.retention_chart?.length ? dashboard.retention_chart : retentionSeries,
    dataUsage: dashboard?.data_usage_chart?.length ? dashboard.data_usage_chart : dataUsageSeries,
    packageUtilization: dashboard?.package_utilization?.length ? dashboard.package_utilization : packageUtilization,
    forecast: dashboard?.revenue_forecast?.length ? dashboard.revenue_forecast : forecastSeries,
    sms: dashboard?.sms_chart?.length ? dashboard.sms_chart : smsSeries,
    network: dashboard?.data_usage_chart?.length ? dashboard.data_usage_chart.slice(-3) : networkDataSeries,
    mostActiveUsers: dashboard?.most_active_users?.length ? dashboard.most_active_users : mostActiveUsers.map(([username, data_used, phone]) => ({ username, data_used, phone })),
    packagePerformance: dashboard?.package_performance?.length ? dashboard.package_performance : packagePerformance.map(([name, price, active_users, monthly_revenue, avg_data_usage, arpu]) => ({ name, price, active_users, monthly_revenue, avg_data_usage, arpu })),
  };

  if (loading) {
    return <div className={`rounded-lg p-4 text-xs ${darkMode ? 'bg-[#17181b] text-[#c8ccdc]' : 'bg-white text-slate-600'}`}>Loading dashboard...</div>;
  }

  return (
    <div className={`min-h-[calc(100vh-96px)] space-y-4 rounded-lg p-4 ${darkMode ? 'bg-[#17181b] text-white' : 'bg-white text-slate-950'}`}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-lg font-semibold">Good morning, Expresswifi 🇰🇪</h1>
        <div className="flex gap-2">
          <button type="button" className="inline-flex h-8 items-center gap-2 rounded-md bg-red-600 px-3 text-[11px] font-semibold text-white"><AlertTriangle size={14} />Expires in 2 days. Click to renew</button>
          <button type="button" className="inline-flex h-8 items-center gap-2 rounded-md border border-[#3a3b40] bg-[#25262a] px-3 text-[11px] font-semibold"><Filter size={14} />Filters</button>
        </div>
      </div>

      <section className="grid gap-4 lg:grid-cols-3">
        <TopStat icon={CreditCard} label="Amount this month" value={`KSh ${stats.amountThisMonth.toLocaleString()}`} helper="Total earned this month" />
        <TopStat icon={MessageSquare} label="SMS balance" value={`KSh ${stats.smsBalance.toFixed(2)}`} helper="Your SMS balance" />
        <TopStat icon={Users} label="Total clients" value={stats.totalClients} helper="Number of clients" />
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <ChartCard darkMode={darkMode} title="Payments" subtitle="Payments and expenses trend."><BarChart data={chartData.payments} height={230} /></ChartCard>
        <ChartCard darkMode={darkMode} title="Active Users" subtitle={`Active now: ${stats.activeClients} users`}><LineChart data={chartData.activeUsers} indexes={[1, 2]} colors={[ORANGE, '#f8dcc7']} height={230} /></ChartCard>
        <ChartCard darkMode={darkMode} title="Customer retention rate (6 months)" subtitle="How many customers are recurring and how many are churning?"><LineChart data={chartData.retention} indexes={[1, 2, 3, 4]} colors={['#3b82f6', '#10b981', '#ef4444', '#f59e0b']} height={230} /></ChartCard>
        <ChartCard darkMode={darkMode} title="Data Usage" subtitle="Data usage trend for PPPoE and Hotspot users"><LineChart data={chartData.dataUsage} indexes={[1]} colors={[ORANGE]} height={230} /></ChartCard>
        <ChartCard darkMode={darkMode} title="Package Utilization" subtitle="Distribution of packages in use."><DonutChart data={chartData.packageUtilization} /></ChartCard>
        <ChartCard darkMode={darkMode} title="Revenue Forecast (3 months)" subtitle="How much revenue will you expect to generate in the next 3 months?"><LineChart data={chartData.forecast} indexes={[1]} colors={['#3b82f6']} height={230} /></ChartCard>
        <ChartCard darkMode={darkMode} title="Sent SMS" subtitle="SMS sent from the system."><BarChart data={chartData.sms} height={230} /></ChartCard>
        <ChartCard darkMode={darkMode} title="Network Data Usage" subtitle="Total download trend this week"><AreaChart data={chartData.network} /></ChartCard>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <ChartCard darkMode={darkMode} title="User Registrations" subtitle="User registration trend."><BarChart data={[['Thu', 2], ['Fri', 7], ['Sat', 3], ['Sun', 2], ['Mon', 6], ['Tue', 0], ['Wed', 0]]} height={230} /></ChartCard>
        <section className={`rounded-lg border ${darkMode ? 'border-[#33343a] bg-[#222326] text-white' : 'border-slate-200 bg-white text-slate-950'}`}>
          <div className="border-b border-[#36373d] px-4 py-3">
            <h2 className="text-sm font-semibold">Most Active Users</h2>
            <p className="mt-1 text-[11px] text-[#a9aec3]">The most active users in the last 30 days.</p>
          </div>
          <table className="min-w-full divide-y divide-[#36373d] text-xs">
            <thead className="bg-[#2a2b2f] text-left text-[10px] uppercase text-[#d5d7e2]"><tr><th className="px-4 py-3">Username</th><th className="px-4 py-3">Data Used</th><th className="px-4 py-3">Phone</th></tr></thead>
            <tbody className="divide-y divide-[#34353b]">
              {chartData.mostActiveUsers.map((user) => <tr key={user.username}><td className="px-4 py-3 font-semibold text-[#ff8a00]">{user.username}</td><td className="px-4 py-3">{user.data_used}</td><td className="px-4 py-3 font-semibold text-[#ff8a00]">{user.phone}</td></tr>)}
            </tbody>
          </table>
          <div className="flex justify-end p-3"><button className="rounded-md border border-[#3a3b40] bg-[#292a2e] px-3 py-2 text-[11px] font-semibold">Next</button></div>
        </section>
      </section>

      <section className={`rounded-lg border ${darkMode ? 'border-[#33343a] bg-[#222326] text-white' : 'border-slate-200 bg-white text-slate-950'}`}>
        <div className="flex flex-col gap-3 border-b border-[#36373d] px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="text-sm font-semibold">Package Performance Comparison</h2>
          <input className="h-8 rounded-md border border-[#3a3b40] bg-[#292a2e] px-3 text-xs text-white outline-none" placeholder="Search" />
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-[900px] divide-y divide-[#36373d] text-xs">
            <thead className="bg-[#2a2b2f] text-left text-[10px] uppercase text-[#d5d7e2]"><tr><th className="px-4 py-3">Package Name</th><th className="px-4 py-3">Price</th><th className="px-4 py-3">Active Users</th><th className="px-4 py-3">Monthly Revenue</th><th className="px-4 py-3">Avg. Data Usage</th><th className="px-4 py-3">ARPU</th></tr></thead>
            <tbody className="divide-y divide-[#34353b]">
              {chartData.packagePerformance.map((row) => <tr key={row.name} className="odd:bg-[#202125] even:bg-[#28282d]"><td className="px-4 py-4 font-bold uppercase text-white">{row.name}</td><td className="px-4 py-4">KSh {Number(row.price || 0).toLocaleString()}</td><td className="px-4 py-4"><span className="rounded bg-[#754619] px-2 py-1 text-[10px] text-[#ffc38d]">{row.active_users}</span></td><td className="px-4 py-4">KSh {Number(row.monthly_revenue || 0).toLocaleString()}</td><td className="px-4 py-4">{row.avg_data_usage} GB</td><td className="px-4 py-4">KSh {Number(row.arpu || 0).toLocaleString()}</td></tr>)}
            </tbody>
          </table>
        </div>
        <div className="flex justify-center p-4"><button className="rounded-md border border-[#3a3b40] bg-[#292a2e] px-3 py-2 text-[11px] font-semibold text-[#d8dbe8]">Per page&nbsp;&nbsp;10</button></div>
      </section>
    </div>
  );
}
