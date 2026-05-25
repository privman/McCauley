import { useEffect, useState } from "react";
import { api, User } from "../api";
import { LocaleSelector } from "../components/LocaleSelector";
import { useLocale } from "../i18n/LocaleContext";

export default function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [users, setUsers] = useState<User[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { t } = useLocale();

  useEffect(() => {
    api
      .listUsers()
      .then(setUsers)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <div className="p-8 text-rose-600">{error}</div>;
  if (!users) return <div className="p-8 text-slate-500">{t("login.loading_users")}</div>;

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <div className="bg-white shadow rounded-xl p-8 w-full max-w-md">
        <div className="flex items-start justify-between mb-2">
          <h1 className="text-xl font-semibold text-slate-800">McCauley</h1>
          <LocaleSelector />
        </div>
        <p className="text-slate-500 mb-6 text-sm">{t("login.subtitle")}</p>
        <ul className="divide-y divide-slate-100">
          {users.map((u) => (
            <li key={u.id}>
              <button
                onClick={async () => onLogin(await api.login(u.id))}
                className="w-full text-left py-3 px-2 hover:bg-slate-50 flex items-baseline gap-3"
              >
                <span className="font-medium text-slate-800">{u.name}</span>
                <span className="text-slate-500 text-sm">{u.title}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
