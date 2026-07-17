import { Pencil, Plus, Router, Trash2, WifiOff } from 'lucide-react';
import { useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import StatusBadge from '../components/StatusBadge';

const initialEquipment = [
  { id: 'EQ-001', name: 'RB4011 Core', type: 'MikroTik Router', location: 'Server room', serial: 'RB4011-EXP-001', assignedTo: 'Network', status: 'online' },
  { id: 'EQ-002', name: 'AP Block A', type: 'Access Point', location: 'Block A roof', serial: 'CAP-AX-018', assignedTo: 'Field Team', status: 'online' },
  { id: 'EQ-003', name: 'CPE House 17', type: 'Customer CPE', location: 'House 17', serial: 'CPE-017', assignedTo: 'Mary Wanjiku', status: 'offline' },
];

const blankDevice = { id: '', name: '', type: 'Access Point', location: '', serial: '', assignedTo: '', status: 'online' };

export default function Equipment() {
  const [devices, setDevices] = useState(initialEquipment);
  const [draft, setDraft] = useState(blankDevice);
  const [editingId, setEditingId] = useState(null);
  const grouped = useMemo(() => devices.reduce((map, item) => ({ ...map, [item.type]: [...(map[item.type] || []), item] }), {}), [devices]);

  const save = (event) => {
    event.preventDefault();
    const payload = { ...draft, id: draft.id || `EQ-${Date.now().toString().slice(-4)}` };
    setDevices((current) => (editingId ? current.map((item) => (item.id === editingId ? payload : item)) : [payload, ...current]));
    setDraft(blankDevice);
    setEditingId(null);
    toast.success('Equipment saved');
  };

  const remove = (device) => {
    setDevices((current) => current.filter((item) => item.id !== device.id));
    toast.success('Equipment deleted');
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="page-title">Equipment</h1>
          <p className="page-subtitle">Track routers, access points, radios, and customer CPE devices.</p>
        </div>
        <div className="flex gap-2">
          <span className="btn-secondary"><Router size={15} />{devices.filter((d) => d.status === 'online').length} online</span>
          <span className="btn-secondary"><WifiOff size={15} />{devices.filter((d) => d.status !== 'online').length} needs attention</span>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[0.75fr_1.25fr]">
        <form className="surface-card p-4" onSubmit={save}>
          <h2 className="mb-4 text-sm font-normal text-slate-950">{editingId ? 'Edit equipment' : 'Add equipment'}</h2>
          <div className="space-y-3">
            <input className="form-input" placeholder="Device name" value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} />
            <select className="form-input" value={draft.type} onChange={(e) => setDraft((d) => ({ ...d, type: e.target.value }))}><option>MikroTik Router</option><option>Access Point</option><option>Radio</option><option>Customer CPE</option><option>UPS</option></select>
            <input className="form-input" placeholder="Location" value={draft.location} onChange={(e) => setDraft((d) => ({ ...d, location: e.target.value }))} />
            <input className="form-input" placeholder="Serial number" value={draft.serial} onChange={(e) => setDraft((d) => ({ ...d, serial: e.target.value }))} />
            <input className="form-input" placeholder="Assigned to" value={draft.assignedTo} onChange={(e) => setDraft((d) => ({ ...d, assignedTo: e.target.value }))} />
            <select className="form-input" value={draft.status} onChange={(e) => setDraft((d) => ({ ...d, status: e.target.value }))}><option value="online">Online</option><option value="offline">Offline</option><option value="degraded">Degraded</option><option value="maintenance">Maintenance</option></select>
          </div>
          <button className="btn-primary mt-4 w-full" type="submit"><Plus size={15} />Save device</button>
        </form>

        <section className="space-y-4">
          {Object.entries(grouped).map(([type, items]) => (
            <div key={type} className="surface-card p-4">
              <h2 className="mb-3 text-sm font-normal text-slate-950">{type}</h2>
              <div className="grid gap-3">
                {items.map((device) => (
                  <article key={device.id} className="flex flex-col gap-3 rounded-md border border-slate-200 p-3 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <p className="text-sm font-medium text-slate-950">{device.name}</p>
                      <p className="mt-1 text-xs text-slate-500">{device.location} - {device.serial} - {device.assignedTo}</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge status={device.status} />
                      <button className="btn-secondary" type="button" onClick={() => { setDraft(device); setEditingId(device.id); }}><Pencil size={14} />Edit</button>
                      <button className="btn-danger" type="button" onClick={() => remove(device)}><Trash2 size={14} />Delete</button>
                    </div>
                  </article>
                ))}
              </div>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}
