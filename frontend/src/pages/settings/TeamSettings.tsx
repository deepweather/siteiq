import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { TextField, FormError, SubmitButton } from '../../components/auth/fields';
import { useAuth } from '../../lib/auth/AuthProvider';
import {
  ApiError,
  type AuditEvent,
  type InviteRow,
  type MemberRow,
  orgs,
} from '../../services/api';

const InviteSchema = z.object({
  email: z.string().email('Enter a valid email'),
  role: z.enum(['admin', 'member', 'viewer']),
});
type InviteForm = z.infer<typeof InviteSchema>;

const ROLE_DESC: Record<string, string> = {
  owner: 'Full control. Can delete the workspace.',
  admin: 'Manage team, sites, billing.',
  member: 'View + apply optimizations.',
  viewer: 'Read-only access.',
};

export default function TeamSettings() {
  const { user, org } = useAuth();
  const isOwner = org?.role === 'owner';
  const [members, setMembers] = useState<MemberRow[]>([]);
  const [invites, setInvites] = useState<InviteRow[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [serverError, setServerError] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const [m, i] = await Promise.all([orgs.members(), orgs.invites()]);
      setMembers(m);
      setInvites(i);
      if (isOwner) setAudit(await orgs.audit());
    } catch {
      // ignored — error envelope already surfaces in console
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [org?.id]);

  const {
    register,
    handleSubmit,
    setError,
    reset,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<InviteForm>({
    resolver: zodResolver(InviteSchema),
    defaultValues: { role: 'member' },
  });
  const watchedRole = watch('role') ?? 'member';

  const onInvite = async (data: InviteForm) => {
    setServerError(null);
    try {
      await orgs.invite(data.email, data.role);
      reset({ email: '', role: 'member' });
      refresh();
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.field) setError(e.field as keyof InviteForm, { message: e.message });
        else setServerError(e.message);
      } else setServerError('Could not send invite.');
    }
  };

  const onChangeRole = async (userId: string, role: MemberRow['role']) => {
    try {
      await orgs.changeRole(userId, role);
      refresh();
    } catch (e) {
      setServerError(e instanceof ApiError ? e.message : 'Could not change role.');
    }
  };

  const onRemove = async (userId: string) => {
    if (!confirm('Remove this member from the workspace?')) return;
    try {
      await orgs.removeMember(userId);
      refresh();
    } catch (e) {
      setServerError(e instanceof ApiError ? e.message : 'Could not remove member.');
    }
  };

  return (
    <div className="space-y-10">
      <section>
        <h1 className="text-2xl font-semibold tracking-tight mb-1">Team</h1>
        <p className="text-sm text-muted-foreground mb-6">
          Manage members and invites for <strong>{org?.name}</strong>.
        </p>
        <form
          onSubmit={handleSubmit(onInvite)}
          className="rounded-xl border border-border bg-card p-6"
          noValidate
        >
          <FormError>{serverError}</FormError>
          <div className="grid grid-cols-1 sm:grid-cols-[1fr_180px_auto] gap-3 items-start">
            <TextField
              label="Invite by email"
              type="email"
              placeholder="teammate@company.com"
              {...register('email')}
              error={errors.email?.message}
            />
            <div>
              <label className="block text-sm font-medium mb-1">Role</label>
              <select
                {...register('role')}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                <option value="admin">Admin</option>
                <option value="member">Member</option>
                <option value="viewer">Viewer</option>
              </select>
              <p className="text-xs text-muted-foreground mt-1">
                {ROLE_DESC[watchedRole]}
              </p>
            </div>
            <div className="self-end">
              <SubmitButton loading={isSubmitting}>Send invite</SubmitButton>
            </div>
          </div>
        </form>
      </section>

      <section>
        <h2 className="text-lg font-semibold tracking-tight mb-3">Members</h2>
        <div className="rounded-xl border border-border bg-card divide-y divide-border">
          {members.map((m) => (
            <div key={m.user_id} className="px-5 py-3 flex items-center gap-4">
              <div className="flex-1 min-w-0">
                <div className="font-medium truncate">{m.name}</div>
                <div className="text-xs text-muted-foreground truncate">{m.email}</div>
              </div>
              <select
                disabled={m.user_id === user?.id || (!isOwner && m.role === 'owner')}
                value={m.role}
                onChange={(e) => onChangeRole(m.user_id, e.target.value as MemberRow['role'])}
                className="rounded-md border border-input bg-background px-2 py-1 text-xs"
              >
                {isOwner && <option value="owner">Owner</option>}
                <option value="admin">Admin</option>
                <option value="member">Member</option>
                <option value="viewer">Viewer</option>
              </select>
              <button
                onClick={() => onRemove(m.user_id)}
                disabled={m.user_id === user?.id}
                className="text-xs text-destructive hover:underline disabled:opacity-40"
              >
                Remove
              </button>
            </div>
          ))}
          {members.length === 0 && (
            <div className="px-5 py-6 text-sm text-muted-foreground text-center">
              No members yet.
            </div>
          )}
        </div>
      </section>

      {invites.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold tracking-tight mb-3">Pending invites</h2>
          <div className="rounded-xl border border-border bg-card divide-y divide-border">
            {invites.map((i) => (
              <div key={i.id} className="px-5 py-3 flex items-center gap-4">
                <div className="flex-1">
                  <div className="font-medium">{i.email}</div>
                  <div className="text-xs text-muted-foreground">
                    {i.role} · expires {new Date(i.expires_at).toLocaleDateString()}
                    {i.expired && <span className="ml-2 text-destructive">expired</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {isOwner && audit.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold tracking-tight mb-3">Audit log</h2>
          <div className="rounded-xl border border-border bg-card divide-y divide-border">
            {audit.slice(0, 20).map((e) => (
              <div key={e.id} className="px-5 py-3 text-sm">
                <span className="font-mono text-xs text-muted-foreground mr-3">
                  {new Date(e.created_at).toLocaleString()}
                </span>
                <span className="font-medium">{e.kind}</span>
                {Object.keys(e.payload).length > 0 && (
                  <span className="ml-2 text-muted-foreground text-xs">
                    {JSON.stringify(e.payload)}
                  </span>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
