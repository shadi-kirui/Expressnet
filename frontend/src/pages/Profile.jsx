import { Save } from 'lucide-react';
import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import api from '../api/axios';

export default function Profile() {
  const [form, setForm] = useState({ owner_name: '', email: '', phone: '', current_password: '', new_password: '', confirm_password: '' });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const { data } = await api.get('/profile');
        setForm((current) => ({ ...current, owner_name: data.owner_name || '', email: data.email || '', phone: data.phone || '' }));
      } catch (error) {
        toast.error(error.response?.data?.message || 'Failed to load profile');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const update = (event) => setForm((current) => ({ ...current, [event.target.name]: event.target.value }));

  const save = async (event) => {
    event.preventDefault();
    try {
      await api.patch('/profile', form);
      toast.success('Profile updated');
      setForm((current) => ({ ...current, current_password: '', new_password: '', confirm_password: '' }));
    } catch (error) {
      toast.error(error.response?.data?.message || 'Failed to update profile');
    }
  };

  if (loading) return <div className="surface-card p-6 text-sm text-slate-400">Loading profile...</div>;

  return (
    <form className="space-y-6" onSubmit={save}>
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h1 className="text-lg font-semibold text-slate-800">Profile</h1>
        <p className="text-sm text-slate-500">Manage your owner details and account password.</p>
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <label className="text-xs text-slate-500">Owner name<input name="owner_name" className="form-input" value={form.owner_name} onChange={update} /></label>
          <label className="text-xs text-slate-500">Phone<input name="phone" className="form-input" value={form.phone} onChange={update} /></label>
          <label className="text-xs text-slate-500 md:col-span-2">Email<input name="email" type="email" className="form-input" value={form.email} onChange={update} /></label>
        </div>
      </section>
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-800">Password</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <label className="text-xs text-slate-500">Current password<input name="current_password" type="password" className="form-input" value={form.current_password} onChange={update} /></label>
          <label className="text-xs text-slate-500">New password<input name="new_password" type="password" className="form-input" value={form.new_password} onChange={update} /></label>
          <label className="text-xs text-slate-500">Confirm new password<input name="confirm_password" type="password" className="form-input" value={form.confirm_password} onChange={update} /></label>
        </div>
      </section>
      <section className="rounded-xl border border-dashed border-slate-300 bg-white p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-800">Two-factor authentication</h2>
        <p className="mt-1 text-sm text-slate-500">Coming soon. This will add an extra verification step for tenant logins.</p>
      </section>
      <button type="submit" className="btn-primary"><Save size={16} />Save profile</button>
    </form>
  );
}
