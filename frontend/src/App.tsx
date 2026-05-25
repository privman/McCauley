import { useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api, User } from "./api";
import { LocaleSelector } from "./components/LocaleSelector";
import { useLocale } from "./i18n/LocaleContext";
import Login from "./pages/Login";
import GiveFeedback from "./pages/GiveFeedback";
import MyFeedback from "./pages/MyFeedback";

export default function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const navigate = useNavigate();
  const { t } = useLocale();

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null));
  }, []);

  if (user === undefined) return <div className="p-8 text-slate-500">{t("app.loading")}</div>;

  if (user === null) {
    return (
      <Routes>
        <Route path="*" element={<Login onLogin={setUser} />} />
      </Routes>
    );
  }

  const logout = async () => {
    await api.logout();
    setUser(null);
    navigate("/");
  };

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <header className="bg-white border-b border-slate-200 shrink-0">
        <div className="max-w-6xl mx-auto px-6 py-3 flex items-center gap-6">
          <h1 className="font-semibold text-slate-800">McCauley</h1>
          <nav className="flex gap-4 text-sm">
            <Link to="/give-feedback" className="text-slate-700 hover:text-slate-900">
              {t("nav.give_feedback")}
            </Link>
            <Link to="/my-feedback" className="text-slate-700 hover:text-slate-900">
              {t("nav.review_feedback")}
            </Link>
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <span className="text-slate-500">
              {user.name} <span className="text-slate-400">· {user.title}</span>
            </span>
            <button onClick={logout} className="text-slate-500 hover:text-slate-800">
              {t("app.sign_out")}
            </button>
            <LocaleSelector />
          </div>
        </div>
      </header>
      <main className="flex-1 min-h-0 max-w-6xl w-full mx-auto p-6 overflow-hidden">
        <Routes>
          <Route path="/give-feedback" element={<GiveFeedback />} />
          <Route path="/my-feedback" element={<MyFeedback />} />
          <Route path="*" element={<Navigate to="/give-feedback" replace />} />
        </Routes>
      </main>
    </div>
  );
}
