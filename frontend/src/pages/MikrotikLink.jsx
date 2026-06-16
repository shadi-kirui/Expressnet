import {
  CheckCircle2,
  Clipboard,
  Eye,
  EyeOff,
  Network,
  RefreshCw,
  Router,
  Save,
  ShieldCheck,
  Wifi,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import api from '../api/axios';

const initialForm = {
  mikrotik_host: '',
  mikrotik_user: '',
  mikrotik_pass: '',
  mikrotik_port: '8728',
};

const initialAssignment = {
  interface: '',
  service_type: 'pppoe',
  profile: 'default',
};

export default function MikrotikSettings() {
  const [form, setForm] = useState(initialForm);
  const [assignment, setAssignment] = useState(initialAssignment);
  const [hasSavedPassword, setHasSavedPassword] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [lastTest, setLastTest] = useState(null);
  const [provision, setProvision] = useState(null);
  const [routerStatus, setRouterStatus] = useState(null);
  const [pullingStatus, setPullingStatus] = useState(false);
  const [assigning, setAssigning] = useState(false);

  const configured = useMemo(
    () => Boolean(form.mikrotik_host && form.mikrotik_user && (form.mikrotik_pass || hasSavedPassword)),
    [form.mikrotik_host, form.mikrotik_pass, form.mikrotik_user, hasSavedPassword],
  );

  const profiles = routerStatus?.profiles?.[assignment.service_type] || [];

  async function loadConfig() {
    setLoading(true);
    try {
      const { data } = await api.get('/settings/mikrotik');
      setForm({
        mikrotik_host: data.mikrotik_host || '',
        mikrotik_user: data.mikrotik_user || '',
        mikrotik_pass: '',
        mikrotik_port: String(data.mikrotik_port || 8728),
      });
      setHasSavedPassword(Boolean(data.has_mikrotik_password));
    } catch (error) {
      toast.error(error.response?.data?.message || 'Failed to load MikroTik settings');
    } finally {
      setLoading(false);
    }
  }

  async function loadProvisionCommand() {
    try {
      const { data } = await api.get('/router/provision-command');
      setProvision(data);
      setForm((current) => ({
        ...current,
        mikrotik_user: current.mikrotik_user || data.api_user || '',
        mikrotik_pass: current.mikrotik_pass || data.api_password || '',
      }));
    } catch (error) {
      toast.error(error.response?.data?.message || 'Failed to create provisioning command');
    }
  }

  useEffect(() => {
    loadConfig();
    loadProvisionCommand();
  }, []);

  const update = (event) => {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
    setLastTest(null);
  };

  const updateAssignment = (event) => {
    const { name, value } = event.target;
    setAssignment((current) => ({
      ...current,
      [name]: value,
      ...(name === 'service_type' ? { profile: 'default' } : {}),
    }));
  };

  const payload = () => {
    const next = {
      mikrotik_host: form.mikrotik_host.trim(),
      mikrotik_user: form.mikrotik_user.trim(),
      mikrotik_port: Number(form.mikrotik_port || 8728),
    };
    if (form.mikrotik_pass.trim()) next.mikrotik_pass = form.mikrotik_pass;
    return next;
  };

  const copy = async (value, label) => {
    try {
      await navigator.clipboard.writeText(value || '');
      toast.success(`${label} copied`);
    } catch {
      toast.error('Copy failed');
    }
  };

  const save = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      const { data } = await api.patch('/settings/mikrotik', payload());
      setHasSavedPassword(Boolean(data.config?.has_mikrotik_password));
      setForm((current) => ({ ...current, mikrotik_pass: '' }));
      toast.success(data.message || 'MikroTik configuration saved');
    } catch (error) {
      toast.error(error.response?.data?.message || 'Failed to save MikroTik settings');
    } finally {
      setSaving(false);
    }
  };

  const testConnection = async () => {
    setTesting(true);
    setLastTest(null);
    try {
      const { data } = await api.post('/settings/mikrotik/test', payload());
      setLastTest({ ok: true, message: data.message, profileCount: data.profile_count });
      toast.success(data.message || 'MikroTik connection successful');
    } catch (error) {
      const message = error.response?.data?.message || 'MikroTik connection failed';
      setLastTest({ ok: false, message });
      toast.error(message);
    } finally {
      setTesting(false);
    }
  };

  const pullRouterStatus = async () => {
    setPullingStatus(true);
    try {
      const { data } = await api.get('/router/status');
      setRouterStatus(data);
      toast.success('Router status pulled');
    } catch (error) {
      toast.error(error.response?.data?.message || 'Failed to pull router status');
    } finally {
      setPullingStatus(false);
    }
  };

  const assignPort = async (event) => {
    event.preventDefault();
    if (!assignment.interface) {
      toast.error('Select a router port');
      return;
    }
    setAssigning(true);
    try {
      const { data } = await api.post('/router/ports', assignment);
      toast.success(data.message || 'Port assigned');
      await pullRouterStatus();
    } catch (error) {
      toast.error(error.response?.data?.message || 'Failed to assign port');
    } finally {
      setAssigning(false);
    }
  };

  if (loading) return <p className="text-sm font-medium text-slate-600">Loading MikroTik configuration...</p>;

  return (
    <div className="space-y-4">
      <section id="link-mikrotik" className="surface-card p-4">
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="page-title">Link MikroTik Device</h1>
            <p className="page-subtitle">Connect the router, pull live device status, and assign ports for PPPoE or Hotspot service.</p>
          </div>
          <div className={`inline-flex h-9 items-center gap-2 rounded-md px-3 text-sm font-medium ${configured ? 'bg-green-50 text-green-700' : 'bg-amber-50 text-amber-700'}`}>
            {configured ? <CheckCircle2 size={17} /> : <Router size={17} />}
            {configured ? 'Configured' : 'Needs setup'}
          </div>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="text-sm font-bold text-slate-950">Provisioning command</h2>
            <p className="mt-1 text-sm text-slate-600">Run this once in the MikroTik terminal to create a dedicated API user for this billing system.</p>
          </div>
          <button type="button" className="btn-secondary" onClick={loadProvisionCommand}>
            <RefreshCw size={16} />
            New Command
          </button>
        </div>
        <div className="mt-4 rounded-lg bg-slate-950 p-4 text-white">
          <div className="flex items-center justify-between gap-3">
            <span className="text-xs font-bold uppercase tracking-wide text-slate-300">Router terminal</span>
            <button type="button" className="btn-secondary border-slate-700 bg-slate-800 text-white hover:bg-slate-700" onClick={() => copy(provision?.command, 'Command')} disabled={!provision?.command}>
              <Clipboard size={15} />
              Copy
            </button>
          </div>
          <pre className="mt-3 max-h-40 overflow-auto whitespace-pre-wrap break-all rounded-md bg-slate-800 p-3 text-xs leading-6 text-slate-100">{provision?.command || 'Generating command...'}</pre>
        </div>
        {provision && (
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
              <p className="text-xs font-semibold uppercase text-slate-500">API username</p>
              <p className="mt-1 font-mono text-sm text-slate-900">{provision.api_user}</p>
            </div>
            <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
              <p className="text-xs font-semibold uppercase text-slate-500">API password</p>
              <button type="button" className="mt-1 font-mono text-sm font-semibold text-app-accent" onClick={() => copy(provision.api_password, 'API password')}>
                Copy generated password
              </button>
            </div>
          </div>
        )}
      </section>

      <form className="surface-card p-4" onSubmit={save}>
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="form-label" htmlFor="mikrotik_host">Router host</label>
            <input id="mikrotik_host" name="mikrotik_host" className="form-input" value={form.mikrotik_host} onChange={update} placeholder="192.168.88.1 or router.example.com" />
          </div>
          <div>
            <label className="form-label" htmlFor="mikrotik_port">API port</label>
            <input id="mikrotik_port" name="mikrotik_port" type="number" min="1" max="65535" className="form-input" value={form.mikrotik_port} onChange={update} />
          </div>
          <div>
            <label className="form-label" htmlFor="mikrotik_user">API username</label>
            <input id="mikrotik_user" name="mikrotik_user" className="form-input" value={form.mikrotik_user} onChange={update} placeholder="billing-api" />
          </div>
          <div>
            <label className="form-label" htmlFor="mikrotik_pass">API password</label>
            <div className="relative">
              <input id="mikrotik_pass" name="mikrotik_pass" type={showPassword ? 'text' : 'password'} className="form-input pr-11" value={form.mikrotik_pass} onChange={update} placeholder={hasSavedPassword ? 'Leave blank to keep saved password' : ''} />
              <button type="button" className="absolute right-2 top-1/2 inline-flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-md text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-100" aria-label={showPassword ? 'Hide password' : 'Show password'} onClick={() => setShowPassword((current) => !current)}>
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-col gap-3 border-t border-slate-200 pt-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2 text-sm text-slate-600">
            <ShieldCheck size={17} className="text-app-accent" />
            <span>{hasSavedPassword ? 'A router password is saved.' : 'No router password is saved yet.'}</span>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn-secondary" onClick={testConnection} disabled={testing || saving}>
              <Wifi size={17} />
              {testing ? 'Testing...' : 'Test Connection'}
            </button>
            <button type="submit" className="btn-primary" disabled={saving || testing}>
              <Save size={17} />
              {saving ? 'Saving...' : 'Save Configuration'}
            </button>
          </div>
        </div>
      </form>

      {lastTest && (
        <section className={`rounded-lg border p-4 ${lastTest.ok ? 'border-green-200 bg-green-50 text-green-800' : 'border-red-200 bg-red-50 text-red-700'}`}>
          <p className="text-sm font-medium">{lastTest.message}</p>
          {lastTest.ok && <p className="mt-1 text-sm">PPP profiles found: {lastTest.profileCount}</p>}
        </section>
      )}

      <section className="surface-card p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-sm font-bold text-slate-950">Router status and ports</h2>
            <p className="mt-1 text-sm text-slate-600">Pull live device details, profiles, active services, and physical interfaces from the router.</p>
          </div>
          <button type="button" className="btn-primary" onClick={pullRouterStatus} disabled={pullingStatus || !configured}>
            <Network size={17} />
            {pullingStatus ? 'Pulling...' : 'Pull Router Config'}
          </button>
        </div>

        {routerStatus && (
          <div className="mt-4 space-y-4">
            <div className="grid gap-3 md:grid-cols-4">
              {[
                ['Board', routerStatus.device?.board_name || '-'],
                ['RouterOS', routerStatus.device?.version || '-'],
                ['Uptime', routerStatus.device?.uptime || '-'],
                ['CPU', `${routerStatus.device?.cpu_load ?? '-'}%`],
              ].map(([label, value]) => (
                <div key={label} className="rounded-md border border-slate-200 bg-white p-3">
                  <p className="text-xs font-semibold uppercase text-slate-500">{label}</p>
                  <p className="mt-1 text-sm font-semibold text-slate-950">{value}</p>
                </div>
              ))}
            </div>

            <form className="grid gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3 md:grid-cols-[1fr_1fr_1fr_auto]" onSubmit={assignPort}>
              <select className="form-input" name="interface" value={assignment.interface} onChange={updateAssignment}>
                <option value="">Select port</option>
                {routerStatus.interfaces?.map((item) => (
                  <option key={item.name} value={item.name}>{item.name}</option>
                ))}
              </select>
              <select className="form-input" name="service_type" value={assignment.service_type} onChange={updateAssignment}>
                <option value="pppoe">PPPoE</option>
                <option value="hotspot">Hotspot</option>
              </select>
              <select className="form-input" name="profile" value={assignment.profile} onChange={updateAssignment}>
                <option value="default">default</option>
                {profiles.map((profile) => (
                  <option key={profile.name} value={profile.name}>{profile.name}</option>
                ))}
              </select>
              <button type="submit" className="btn-primary" disabled={assigning}>
                {assigning ? 'Assigning...' : 'Assign Port'}
              </button>
            </form>

            <div className="table-shell overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200">
                <thead className="table-head">
                  <tr>
                    <th className="px-4 py-3">Port</th>
                    <th className="px-4 py-3">Type</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Assignment</th>
                    <th className="px-4 py-3">Comment</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {routerStatus.interfaces?.map((item) => {
                    const assigned = routerStatus.assignments?.[item.name];
                    return (
                      <tr key={item.id || item.name}>
                        <td className="table-cell font-medium text-slate-950">{item.name}</td>
                        <td className="table-cell">{item.type || '-'}</td>
                        <td className="table-cell">{item.disabled ? 'Disabled' : item.running ? 'Running' : 'Idle'}</td>
                        <td className="table-cell">{assigned ? `${assigned.service_type?.toUpperCase()} / ${assigned.profile}` : '-'}</td>
                        <td className="table-cell">{item.comment || '-'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
