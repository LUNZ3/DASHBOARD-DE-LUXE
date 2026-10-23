                                      [(f.name, f.getvalue()) for f in files])
                st.success("Application submitted. An administrator will review it.")
                st.rerun()
            except db.StrykeError as ex:
                st.error(str(ex))


def page_coach_dash():
    if not my_coach:
        st.error("No coach profile on this account.")
        return
    c = my_coach
    st.markdown(f"## Coach dashboard · {e(c['name'])}")
    st.markdown(badges(c), unsafe_allow_html=True)
    bs = db.coach_bookings(c["id"])
    done = [b for b in bs if b["status"] == "completed"]
    gross = sum(b["price_cents"] for b in done)
    fees = sum(b["fee_cents"] for b in done)
    m = st.columns(3)
    m[0].metric("Completed sessions", len(done))
    m[1].metric("Gross (completed)", db.money(gross, c["currency"]))
    m[2].metric(f"Your earnings after {db.COMMISSION_PCT:g}% fee", db.money(gross - fees, c["currency"]))
    st.caption("Figures come from persisted bookings. Payouts are not wired yet (no payment provider connected).")
    st.markdown("### Sessions")
    for b in bs:
        with st.container(border=True):
            st.markdown(f"{fmt_slot(db._p(b['start_utc']), c['tz'])} · {e(b['customer_name'])} · **{b['status']}**")
            if b["status"] == "confirmed" and db._p(b["start_utc"]) <= datetime.now(timezone.utc):
                if st.button("Mark completed", key=f"mc{b['id']}"):
                    try:
                        db.complete_booking(user["id"], b["id"])
                        st.rerun()
                    except (db.StrykeError, PermissionError) as ex:
                        st.error(str(ex))
    st.markdown("### Weekly availability")
    st.caption(f"Times in {c['tz']}. Weekday 0 = Monday … 6 = Sunday. Session length is set below.")
    rows = st.data_editor(db.get_availability(c["id"]), num_rows="dynamic", key="avail",
                          column_config={"weekday": st.column_config.NumberColumn("weekday", min_value=0, max_value=6, step=1),
                                         "start_t": "start (HH:MM)", "end_t": "end (HH:MM)"})
    if st.button("Save availability"):
        try:
            db.set_availability(user["id"], rows.to_dict("records") if hasattr(rows, "to_dict") else list(rows))
            st.success("Availability saved.")
        except (db.StrykeError, KeyError, TypeError, ValueError) as ex:
            st.error(str(ex) if isinstance(ex, db.StrykeError) else "Fill in every row completely.")
    st.markdown("### Profile & pricing")
    with st.form("prof"):
        price = st.number_input("Price per session", 0, 5000, c["price_cents"] // 100)
        mins = st.selectbox("Session length (min)", [30, 45, 60, 90, 120], [30, 45, 60, 90, 120].index(c["session_minutes"]))
        bio = st.text_area("Biography", c["bio"])
        style = st.text_input("Coaching style", c["style"])
        if st.form_submit_button("Save profile"):
            try:
                db.update_coach(user["id"], {"price_cents": int(price) * 100, "session_minutes": mins, "bio": bio, "style": style})
                st.success("Saved. (Verification status can only be changed by an administrator.)")
            except db.StrykeError as ex:
                st.error(str(ex))


def page_admin():
    if not db.is_admin(user):  # enforced server-side in every db function too
        st.error("Not authorised.")
        return
    st.markdown("## Admin")
    t = st.tabs(["Applications", "Metrics", "Coaches & users", "Bookings", "Audit log"])
    with t[0]:
        apps = db.list_applications(user)
        if not apps:
            st.info("No applications.")
        for a in apps:
            with st.expander(f"#{a['id']} · {a['data'].get('full_name')} · {a['status']}"):
                st.json(a["data"])
                for fn in a["files"]:
                    st.download_button(f"Download {fn}", db.read_evidence(user, a["id"], fn), file_name=fn, key=f"dl{a['id']}{fn}")
                note = st.text_input("Note to applicant (required for reject / more info)", key=f"n{a['id']}")
                cs = st.columns(4)
                for col, (lbl, stt) in zip(cs, [("Start review", "under_review"), ("Request info", "needs_info"),
                                                ("Approve ✓", "approved"), ("Reject", "rejected")]):
                    if col.button(lbl, key=f"{stt}{a['id']}"):
                        try:
                            db.review_application(user, a["id"], stt, note)
                            st.rerun()
                        except db.StrykeError as ex:
                            st.error(str(ex))
    with t[1]:
        for k, v in db.metrics(user).items():
            st.metric(k, v)
    tb = db.admin_tables(user)
    with t[2]:
        st.dataframe(tb["coaches"])
        cid = st.number_input("Coach id to suspend/unsuspend", 1, 100000, 1)
        c1, c2 = st.columns(2)
        if c1.button("Suspend coach"):
            db.set_suspended(user, "coach", int(cid), True)
            st.rerun()
        if c2.button("Unsuspend coach"):
            db.set_suspended(user, "coach", int(cid), False)
            st.rerun()
        st.dataframe(tb["users"])
    with t[3]:
        st.dataframe(tb["bookings"])
    with t[4]:
        st.dataframe(tb["audit"])


def page_legal():
    st.markdown("## Privacy & Terms (DRAFT)")
    st.markdown('<div class="banner">Placeholder drafts. Must be reviewed and completed by a qualified lawyer before launch.</div>', unsafe_allow_html=True)
    st.markdown("**Privacy (draft).** STRYKE stores account details, bookings and coach applications. Coach evidence is private and visible only to administrators. "
                "Location is used only after you grant browser permission and is not stored.")
    st.markdown("**Terms (draft).** STRYKE is a marketplace connecting customers and independent coaches. Training carries injury risk. "
                "Cancellation: free up to the configured window; later cancellations are not refunded.")


header()
{"home": page_home, "coaches": page_coaches, "profile": page_profile, "account": page_account, "dashboard": page_dashboard,
 "apply": page_apply, "coach_dash": page_coach_dash, "admin": page_admin, "legal": page_legal}.get(ss.page, page_home)()
st.divider()
fc = st.columns([1, 1, 4])
fc[0].button("Privacy & Terms", on_click=nav, args=("legal",), key="legal")
fc[2].caption("STRYKE · Find your coach. Train like a fighter.")

