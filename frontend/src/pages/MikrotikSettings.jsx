import { HelpCircle, Link as LinkIcon, MoreVertical, RefreshCw, Search, Wifi, WifiOff } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { useNavigate } from 'react-router-dom';
import api from '../api/axios';

export default function MikrotikSettings() {
  const navigate = useNavigate();
  const [config, setConfig] = useState(null);
  const [routerStatus, setRouterStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [diagnosing, setDiagnosing] = useState(false);
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');

  const configured = Boolean(config?.mikrotik_host && config?.mikrotik_user && config?.has_mikrotik_password);

  const rows = useMemo(() => {
    if (!configured) return [];
    return [
      {
        id: 'primary',
        boardName: routerStatus?.device?.board_name || config.mikrotik_host || 'MikroTik Router',
        provisioning: 'Completed',
        cpu: routerStatus?.device?.cpu_load,
        memory: routerStatus?.device?.free_memory,
        status: routerStatus ? 'online' : 'offline',
        remoteWinbox: `${config.mikrotik_host}:8291`,
      },
    ];
  }, [config, configured, routerStatus]);

  const counts = useMemo(() => ({
    all: rows.length,
    online: rows.filter((item) => item.status === 'online').length,
    offline: rows.filter((item) => item.status !== 'online').length,
  }), [rows]);

  const filteredRows = rows.filter((item) => {
    const text = `${item.boardName} ${item.remoteWinbox} ${item.provisioning}`.toLowerCase();
    if (!text.includes(search.toLowerCase())) return false;
    if (filter === 'online') return item.status === 'online';
    if (filter === 'offline') return item.status !== 'online';
    return true;
  });

  async function loadConfig() {
    setLoading(true);
    try {
      const { data } = await api.get('/settings/mikrotik');
      setConfig(data);
    } catch (error) {
      toast.error(error.response?.data?.message || 'Failed to load MikroTik routers');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadConfig();
  }, []);

  const diagnose = async () => {
    if (!configured) {
      navigate('/mikrotik/link');
      return;
    }
    setDiagnosing(true);
    try {
      const { data } = await api.get('/router/status');
      setRouterStatus(data);
      toast.success('Router status updated');
    } catch (error) {
      setRouterStatus(null);
      toast.error(error.response?.data?.message || 'Router is offline');
    } finally {
      setDiagnosing(false);
    }
  };

  if (loading) return <p className="text-sm font-medium text-slate-600">Loading MikroTik routers...</p>;

  return (
    <div className="space-y-6">
      <section>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="page-title">MikroTik Routers</h1>
            <p className="page-subtitle">Manage your MikroTik routers on this page</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn-secondary border-slate-300 text-blue-600" onClick={() => toast('Tutorial content will open here when added.')}>
              <HelpCircle size={16} />
              Tutorial
            </button>
            <button type="button" className="btn-primary bg-orange-500 text-slate-950 hover:bg-orange-400" onClick={() => navigate('/mikrotik/link')}>
              <LinkIcon size={16} />
              Link a MikroTik
            </button>
          </div>
        </div>
      </section>

      <section>
        <div className="border-b border-slate-200">
          <div className="flex flex-wrap gap-5">
            {[
              ['all', 'All', counts.all, WifiOff],
              ['online', 'Online', counts.online, Wifi],
              ['offline', 'Offline', counts.offline, WifiOff],
            ].map(([key, label, count, Icon]) => (
              <button
                key={key}
                type="button"
                className={`inline-flex h-10 items-center gap-2 border-b px-1 text-xs font-medium ${
                  filter === key ? 'border-orange-500 text-orange-600' : 'border-transparent text-slate-600'
                }`}
                onClick={() => setFilter(key)}
              >
                <Icon size={15} className="text-slate-400" />
                {label}
                <span className={`rounded px-1.5 py-0.5 text-[10px] ${key === 'online' ? 'bg-green-50 text-green-700' : key === 'offline' ? 'bg-red-50 text-red-600' : 'bg-orange-50 text-orange-700'}`}>{count}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="mt-5 table-shell">
          <div className="flex justify-end border-b border-slate-200 p-3">
            <label className="relative block w-full sm:w-72">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={17} />
              <input className="form-input mt-0 pl-9" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search" />
            </label>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-[900px] divide-y divide-slate-200">
              <thead className="table-head">
                <tr>
                  <th className="px-4 py-3">Board Name</th>
                  <th className="px-4 py-3">Provisioning</th>
                  <th className="px-4 py-3">CPU</th>
                  <th className="px-4 py-3">Memory</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Remote Winbox</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredRows.length === 0 ? (
                  <tr>
                    <td className="table-cell text-slate-500" colSpan="7">No MikroTik routers linked yet.</td>
                  </tr>
                ) : filteredRows.map((router) => (
                  <tr key={router.id}>
                    <td className="table-cell font-medium text-slate-950">{router.boardName}</td>
                    <td className="table-cell"><span className="rounded bg-orange-50 px-2 py-1 text-[11px] font-medium text-orange-700">{router.provisioning}</span></td>
                    <td className="table-cell">{router.cpu === undefined ? '-' : <span className="rounded bg-green-50 px-2 py-1 text-[11px] font-medium text-green-700">{router.cpu}%</span>}</td>
                    <td className="table-cell">{router.memory ? <span className="rounded bg-orange-50 px-2 py-1 text-[11px] font-medium text-orange-700">{router.memory}</span> : '-'}</td>
                    <td className="table-cell">
                      <span className={`rounded px-2 py-1 text-[11px] font-medium ${router.status === 'online' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-600'}`}>
                        {router.status === 'online' ? 'Online' : 'Offline'}
                      </span>
                    </td>
                    <td className="table-cell text-green-700">{router.remoteWinbox}</td>
                    <td className="table-cell">
                      <div className="flex justify-end gap-2">
                        <button type="button" className="btn-secondary border-orange-200 text-orange-600" onClick={diagnose} disabled={diagnosing}>
                          <RefreshCw size={15} className={diagnosing ? 'animate-spin' : ''} />
                          Diagnose
                        </button>
                        <button type="button" className="btn-primary bg-orange-500 text-slate-950 hover:bg-orange-400" onClick={() => navigate('/mikrotik/link')}>
                          <MoreVertical size={15} />
                          Actions
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3 text-xs text-slate-600">
            <span>Showing {filteredRows.length} result{filteredRows.length === 1 ? '' : 's'}</span>
            <span className="rounded-md border border-slate-200 px-3 py-2">Per page&nbsp;&nbsp;10</span>
          </div>
        </div>
      </section>
    </div>
  );
}
