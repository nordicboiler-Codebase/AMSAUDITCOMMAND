import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, UserCog } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { EmptyState, PageHeader, SectionCard } from "@/components/ui/page";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";

interface AdminUser {
  id: string;
  username: string;
  email: string;
  role: "ADMIN" | "AUDITOR" | "VIEWER";
  is_active: boolean;
  mfa_enabled: boolean;
}

export function AdminPage() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);

  const { data: users = [] } = useQuery({
    queryKey: ["users"],
    queryFn: () => api.get<AdminUser[]>("/api/users"),
  });

  return (
    <>
      <PageHeader
        title="Users"
        description="Platform user directory. Manage roles and activation status."
        actions={<Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> New user</Button>}
      />

      {users.length === 0 ? (
        <EmptyState
          icon={<UserCog className="h-5 w-5" />}
          title="No users"
          description="Your admin account created this system. Invite colleagues here."
        />
      ) : (
        <SectionCard title={`${users.length} users`}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b text-[11px] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="text-left font-semibold py-2 px-3">Username</th>
                  <th className="text-left font-semibold py-2 px-3">Email</th>
                  <th className="text-left font-semibold py-2 px-3">Role</th>
                  <th className="text-left font-semibold py-2 px-3">MFA</th>
                  <th className="text-left font-semibold py-2 px-3">Status</th>
                  <th className="text-left font-semibold py-2 px-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {users.map((u) => <UserRow key={u.id} user={u} onChange={() =>
                  qc.invalidateQueries({ queryKey: ["users"] })} />)}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}

      {open && <CreateUserDialog onClose={() => setOpen(false)} onCreated={() => {
        setOpen(false);
        qc.invalidateQueries({ queryKey: ["users"] });
      }} />}
    </>
  );
}

function UserRow({ user, onChange }: { user: AdminUser; onChange: () => void }) {
  const toggle = useMutation({
    mutationFn: () => api.patch(`/api/users/${user.id}`, { is_active: !user.is_active }),
    onSuccess: onChange,
  });
  const changeRole = useMutation({
    mutationFn: (role: string) => api.patch(`/api/users/${user.id}`, { role }),
    onSuccess: onChange,
  });
  return (
    <tr className="hover:bg-secondary/30">
      <td className="py-2 px-3 font-medium">{user.username}</td>
      <td className="py-2 px-3 text-xs text-muted-foreground">{user.email}</td>
      <td className="py-2 px-3">
        <Select
          value={user.role}
          onChange={(e) => changeRole.mutate(e.target.value)}
          className="h-7 py-0 w-[110px]"
        >
          <option value="ADMIN">ADMIN</option>
          <option value="AUDITOR">AUDITOR</option>
          <option value="VIEWER">VIEWER</option>
        </Select>
      </td>
      <td className="py-2 px-3">
        {user.mfa_enabled ? <Badge tone="success">Enabled</Badge> : <Badge tone="muted">Off</Badge>}
      </td>
      <td className="py-2 px-3">
        {user.is_active ? <Badge tone="success">Active</Badge> : <Badge tone="danger">Inactive</Badge>}
      </td>
      <td className="py-2 px-3">
        <Button size="sm" variant="outline" onClick={() => toggle.mutate()}>
          {user.is_active ? "Deactivate" : "Reactivate"}
        </Button>
      </td>
    </tr>
  );
}

function CreateUserDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("AUDITOR");
  const mutation = useMutation({
    mutationFn: () => api.post("/api/users", { username, email, password, role }),
    onSuccess: onCreated,
  });
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-md rounded-lg bg-card border shadow-lg">
        <div className="p-5 border-b"><h3 className="text-base font-semibold">New user</h3></div>
        <div className="p-5 space-y-4">
          <div><Label>Username</Label>
            <Input value={username} onChange={(e) => setUsername(e.target.value)} /></div>
          <div><Label>Email</Label>
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
          <div><Label>Password (≥10 chars, 3 char-classes)</Label>
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></div>
          <div><Label>Role</Label>
            <Select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="VIEWER">VIEWER</option>
              <option value="AUDITOR">AUDITOR</option>
              <option value="ADMIN">ADMIN</option>
            </Select></div>
          {mutation.isError && (
            <div className="text-sm text-destructive">{(mutation.error as Error).message}</div>
          )}
        </div>
        <div className="p-5 border-t flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={() => mutation.mutate()}
                  disabled={!username || !email || !password || mutation.isPending}>
            {mutation.isPending ? "Creating…" : "Create user"}
          </Button>
        </div>
      </div>
    </div>
  );
}
