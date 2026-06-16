import { CreditCard, KeyRound, Package, Phone, Wifi, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { useParams } from 'react-router-dom';
import axios from 'axios';

const publicApi = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'https://genco-production.up.railway.app/api',
});

export default function CustomerPortal() {
  const { tenantId } = useParams();
  const [tenant, setTenant] = useState(null);
  const [packages, setPackages] = useState([]);
  const [phone, setPhone] = useState('');
  const [selectedPackage, setSelectedPackage] = useState(null);
  const [receiptCode, setReceiptCode] = useState('');
  const [recoveredAccess, setRecoveredAccess] = useState(null);
  const [loading, setLoading] = useState(true);
  const [paying, setPaying] = useState(false);
  const [recovering, setRecovering] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [verification, setVerification] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    async function load() {
      try {
        const [tenantRes, packagesRes] = await Promise.all([
          publicApi.get(`/public/${tenantId}`),
          publicApi.get(`/public/${tenantId}/packages`),
        ]);
        setTenant(tenantRes.data);
        setPackages(Array.isArray(packagesRes.data) ? packagesRes.data : []);
      } catch (err) {
        setError(err.response?.data?.message || 'Unable to load packages');
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [tenantId]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const reference = params.get('reference') || params.get('trxref');
    if (!reference) return;
    async function verify() {
      setVerifying(true);
      try {
        const { data } = await publicApi.get(`/public/${tenantId}/verify?reference=${encodeURIComponent(reference)}`);
        setVerification(data);
        if (data.success) toast.success('Payment verified');
      } catch (err) {
        setVerification({ success: false, message: err.response?.data?.message || 'Payment verification failed. Please contact your ISP.' });
      } finally {
        setVerifying(false);
      }
    }
    verify();
  }, [tenantId]);

  const openPayment = (pkg) => {
    setSelectedPackage(pkg);
    setPhone('');
  };

  const closePayment = () => {
    if (!paying) {
      setSelectedPackage(null);
      setPhone('');
    }
  };

  const pay = async () => {
    if (!phone.trim()) {
      toast.error('Enter your phone number');
      return;
    }

    setPaying(true);
    try {
      const { data } = await publicApi.post(`/public/${tenantId}/pay`, {
        package_id: selectedPackage.id,
        phone,
      });
      toast.success(data.message || 'Redirecting to Paystack');
      if (data.authorizationUrl) {
        if (!String(data.authorizationUrl).startsWith('https://checkout.paystack.com/')) {
          toast.error('Payment checkout URL was rejected');
          return;
        }
        window.location.href = data.authorizationUrl;
        return;
      }
      closePayment();
    } catch (err) {
      toast.error(err.response?.data?.message || 'Could not start payment');
    } finally {
      setPaying(false);
    }
  };

  const recover = async (event) => {
    event.preventDefault();
    if (!receiptCode.trim()) {
      toast.error('Enter your payment reference');
      return;
    }

    setRecovering(true);
    setRecoveredAccess(null);
    try {
      const { data } = await publicApi.post(`/public/${tenantId}/redeem`, {
        receipt_code: receiptCode,
      });
      setRecoveredAccess(data);
      toast.success('Access restored');
    } catch (err) {
      toast.error(err.response?.data?.message || 'Could not recover access');
    } finally {
      setRecovering(false);
    }
  };

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-100 px-4">
        <p className="text-sm font-semibold text-slate-600">Loading packages...</p>
      </main>
    );
  }

  if (error) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-100 px-4">
        <section className="max-w-md rounded-lg bg-white p-6 text-center shadow-soft ring-1 ring-slate-200">
          <h1 className="text-xl font-bold text-slate-900">Packages unavailable</h1>
          <p className="mt-2 text-sm text-slate-500">{error}</p>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-100">
      <section className="bg-[#1e3a5f] px-4 py-10 text-white">
        <div className="mx-auto max-w-6xl">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-md bg-blue-600">
              {tenant?.logo_url ? <img src={tenant.logo_url} alt="" className="h-full w-full rounded-md object-cover" /> : <Wifi size={26} />}
            </div>
            <div>
              <p className="text-xs font-bold uppercase tracking-widest text-blue-200">Internet Packages</p>
              <h1 className="text-2xl font-bold sm:text-3xl">{tenant?.business_name || 'Hotspot Portal'}</h1>
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-8">
        {(verifying || verification) && (
          <div className={`mb-6 rounded-lg p-4 shadow-soft ring-1 ${verification?.success ? 'bg-green-50 text-green-800 ring-green-100' : 'bg-white text-slate-700 ring-slate-200'}`}>
            {verifying ? (
              <p className="text-sm font-semibold">Verifying payment...</p>
            ) : verification?.success ? (
              <div className="space-y-1 text-sm">
                <p className="font-bold">Payment successful. Your access is ready.</p>
                <p>Package: {verification.package_name}</p>
                <p>Username: {verification.username}</p>
                <p>Password: {verification.password}</p>
                <p>Expires: {verification.expires_at ? new Date(verification.expires_at).toLocaleString() : '-'}</p>
              </div>
            ) : (
              <div className="text-sm">
                <p className="font-bold text-red-700">Payment not verified</p>
                <p>{verification?.message || 'Please contact your ISP for help.'}</p>
              </div>
            )}
          </div>
        )}
        <div className="mb-6 grid gap-4 lg:grid-cols-[1fr_1.2fr]">
          <div className="rounded-lg bg-white p-4 shadow-soft ring-1 ring-slate-200">
            <div className="flex items-center gap-2">
              <CreditCard size={18} className="text-blue-600" />
              <h2 className="font-bold text-slate-900">Buy a package</h2>
            </div>
            <p className="mt-2 text-sm text-slate-500">Choose a package below, then pay securely through Paystack checkout.</p>
          </div>

          <form className="rounded-lg bg-white p-4 shadow-soft ring-1 ring-slate-200" onSubmit={recover}>
            <label className="form-label" htmlFor="receiptCode">Already paid? Enter payment reference</label>
            <div className="mt-1 flex flex-col gap-3 sm:flex-row">
              <div className="relative flex-1">
                <KeyRound className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                <input
                  id="receiptCode"
                  className="form-input mt-0 pl-10 uppercase"
                  placeholder="e.g. ps_tenant_reference"
                  value={receiptCode}
                  onChange={(event) => setReceiptCode(event.target.value.toUpperCase())}
                />
              </div>
              <button type="submit" className="btn-secondary" disabled={recovering}>
                {recovering ? 'Checking...' : 'Recover Access'}
              </button>
            </div>
            {recoveredAccess && (
              <div className="mt-4 rounded-md bg-green-50 p-3 text-sm text-green-800">
                <p className="font-bold">Access is active</p>
                <p>Username: {recoveredAccess.username}</p>
                <p>Password: {recoveredAccess.password}</p>
                <p>Expires: {new Date(recoveredAccess.expires_at).toLocaleString()}</p>
              </div>
            )}
          </form>
        </div>

        <div className="mb-4 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-xl font-bold text-slate-900">All available packages</h2>
            <p className="text-sm text-slate-500">Pick any package offered by {tenant?.business_name || 'this provider'}.</p>
          </div>
          {packages.length > 0 && (
            <p className="text-sm font-semibold text-slate-600">{packages.length} package{packages.length === 1 ? '' : 's'}</p>
          )}
        </div>

        {packages.length === 0 ? (
          <div className="rounded-lg bg-white p-6 text-center shadow-soft ring-1 ring-slate-200">
            <Package className="mx-auto text-slate-400" size={34} />
            <h2 className="mt-3 text-lg font-bold text-slate-900">No packages available</h2>
            <p className="mt-1 text-sm text-slate-500">Please check again later.</p>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {packages.map((pkg) => (
              <article key={pkg.id} className="rounded-lg bg-white p-5 shadow-soft ring-1 ring-slate-200">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h2 className="text-lg font-bold text-slate-900">{pkg.name}</h2>
                    <p className="mt-1 text-sm text-slate-500">{pkg.speed}</p>
                  </div>
                  <div className="rounded-md bg-blue-50 p-2 text-blue-600">
                    <Wifi size={20} />
                  </div>
                </div>
                <p className="mt-5 text-3xl font-bold text-slate-900">KES {pkg.price}</p>
                <p className="mt-1 text-sm text-slate-500">{pkg.duration_days} days access</p>
                <button
                  type="button"
                  className="btn-primary mt-5 w-full"
                  onClick={() => openPayment(pkg)}
                >
                  <CreditCard size={18} />
                  Pay with Paystack
                </button>
              </article>
            ))}
          </div>
        )}
      </section>

      {selectedPackage && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4">
          <section className="w-full max-w-md rounded-lg bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
              <div>
                <h2 className="text-lg font-bold text-slate-900">{selectedPackage.name}</h2>
                <p className="text-sm text-slate-500">KES {selectedPackage.price} for {selectedPackage.duration_days} days</p>
              </div>
              <button type="button" className="rounded-md p-2 text-slate-500 hover:bg-slate-100" onClick={closePayment} aria-label="Close payment">
                <X size={20} />
              </button>
            </div>
            <div className="p-5">
              <label className="form-label" htmlFor="phone">Phone number</label>
              <div className="relative mt-1">
                <Phone className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                <input
                  id="phone"
                  className="form-input mt-0 pl-10"
                  placeholder="2547XXXXXXXX"
                  value={phone}
                  onChange={(event) => setPhone(event.target.value)}
                />
              </div>
              <button type="button" className="btn-primary mt-5 w-full" onClick={pay} disabled={paying}>
                <CreditCard size={18} />
                {paying ? 'Opening checkout...' : 'Continue to Paystack'}
              </button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
