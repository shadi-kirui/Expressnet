import { Save } from 'lucide-react';
import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import adminApi from '../../api/adminAxios';

const fields = [
  ['brand_name', 'Brand name'],
  ['headline', 'Headline'],
  ['subheadline', 'Subheadline'],
  ['about', 'About us'],
  ['phone', 'Phone'],
  ['email', 'Email'],
  ['location', 'Location'],
  ['address', 'Address'],
  ['cta_label', 'CTA label'],
  ['cta_url', 'CTA URL'],
];

export default function AdminSiteSettings() {
  const [form, setForm] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    adminApi.get('/admin/site')
      .then(({ data }) => setForm(data || {}))
      .catch((error) => toast.error(error.response?.data?.error || 'Failed to load site settings'))
      .finally(() => setLoading(false));
  }, []);

  const update = (event) => {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
  };

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      await adminApi.patch('/admin/site', form);
      toast.success('Site updated');
    } catch (error) {
      toast.error(error.response?.data?.error || 'Failed to update site');
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <p className="text-sm font-medium text-slate-600">Loading site settings...</p>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Site Settings</h1>
        <p className="mt-1 text-sm text-slate-500">Update the public homepage content, contacts, and location.</p>
      </div>
      <form className="rounded-lg bg-white p-6 shadow-soft ring-1 ring-slate-200" onSubmit={submit}>
        <div className="grid gap-4 md:grid-cols-2">
          {fields.map(([name, label]) => (
            <div key={name} className={name === 'about' || name === 'subheadline' ? 'md:col-span-2' : ''}>
              <label className="form-label" htmlFor={name}>{label}</label>
              {name === 'about' || name === 'subheadline' ? (
                <textarea id={name} name={name} className="form-input min-h-28" value={form[name] || ''} onChange={update} />
              ) : (
                <input id={name} name={name} className="form-input" value={form[name] || ''} onChange={update} />
              )}
            </div>
          ))}
        </div>
        <button className="mt-5 inline-flex items-center gap-2 rounded-md bg-[#e94560] px-4 py-2 text-sm font-bold text-white hover:bg-[#c73652]" disabled={saving}>
          <Save size={17} />
          {saving ? 'Saving...' : 'Save Site'}
        </button>
      </form>
    </div>
  );
}
