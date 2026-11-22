import threading
import flet as ft


def DataManageView(db, page):
    state = {"table": "members", "selected_id": None}

    def notify(msg, color=ft.Colors.GREEN_700):
        sb = ft.SnackBar(content=ft.Text(msg, color=ft.Colors.WHITE), bgcolor=color)
        page.open(sb)

    status_label = ft.Text("الجدول الحالي: الأعضاء (0)", size=13, color=ft.Colors.AMBER_200, weight="bold")
    search_input = ft.TextField(label="بحث بالاسم أو الهاتف...", expand=True, dense=True)
    name_input = ft.TextField(label="الاسم الكامل *", expand=True, dense=True)
    phone_input = ft.TextField(label="رقم الهاتف *", expand=True, dense=True, keyboard_type=ft.KeyboardType.PHONE)
    address_input = ft.TextField(label="العنوان / السكن", expand=True, dense=True)
    facebook_input = ft.TextField(label="رابط أو اسم الفيس بوك", expand=True, dense=True)

    role_drop = ft.Dropdown(
        label="الفئة",
        options=[
            ft.dropdown.Option("members", "عضو"),
            ft.dropdown.Option("admins", "مخول"),
        ],
        value="members",
        width=115,
        dense=True,
    )

    data_table = ft.DataTable(
        heading_row_color=ft.Colors.BLUE_GREY_900,
        column_spacing=18,
        columns=[
            ft.DataColumn(ft.Text("ت", weight="bold")),
            ft.DataColumn(ft.Text("الاسم", weight="bold")),
            ft.DataColumn(ft.Text("الهاتف", weight="bold")),
            ft.DataColumn(ft.Text("العنوان", weight="bold")),
            ft.DataColumn(ft.Text("الفيس بوك", weight="bold")),
            ft.DataColumn(ft.Text("تحديد", weight="bold")),
        ],
        rows=[],
    )

    def select_row(row_data):
        state["selected_id"] = row_data[0]
        name_input.value = str(row_data[1] or "")
        phone_input.value = str(row_data[2] or "")
        address_input.value = str(row_data[3] or "")
        facebook_input.value = str(row_data[4] or "")
        role_drop.value = state["table"]
        notify(f"تم تحديد: {row_data[1]} للتعديل أو الحذف", ft.Colors.BLUE_700)
        page.update()

    def load_data(table=None, search_term="", is_init=False):
        if table in ("members", "admins"):
            state["table"] = table
            role_drop.value = table

        records = db.get_records(state["table"], search_term)
        if search_term and len(records) >= 1:
            select_row(records[0])

        data_table.rows.clear()

        for r in records:
            row_copy = tuple(r)
            data_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(r[0]))),
                        ft.DataCell(ft.Text(str(r[1] or ""))),
                        ft.DataCell(ft.Text(str(r[2] or ""))),
                        ft.DataCell(ft.Text(str(r[3] or ""))),
                        ft.DataCell(ft.Text(str(r[4] or ""))),
                        ft.DataCell(
                            ft.IconButton(
                                icon=ft.Icons.EDIT,
                                icon_color=ft.Colors.AMBER,
                                tooltip="اختيار للتعديل",
                                on_click=lambda e, d=row_copy: select_row(d),
                            )
                        ),
                    ]
                )
            )

        if not is_init and (search_term or "").strip() and len(records) >= 1:
            first_r = records[0]
            state["selected_id"] = first_r[0]
            name_input.value = str(first_r[1] or "")
            phone_input.value = str(first_r[2] or "")
            address_input.value = str(first_r[3] or "")
            facebook_input.value = str(first_r[4] or "")
            role_drop.value = state["table"]

        title_ar = "المخولين" if state["table"] == "admins" else "الأعضاء"
        status_label.value = f"الجدول المعروض: {title_ar} | العدد: {len(records)}"

        if not is_init:
            try:
                data_table.update()
            except Exception:
                pass
            page.update()

    def clear_fields(e=None):
        state["selected_id"] = None
        name_input.value = ""
        phone_input.value = ""
        address_input.value = ""
        facebook_input.value = ""
        search_input.value = ""
        load_data(state["table"])

    def add_record(e):
        if not (name_input.value or "").strip() or not (phone_input.value or "").strip():
            notify("يرجى إدخال الاسم ورقم الهاتف أولاً ⚠️", ft.Colors.RED_700)
            return
        target = role_drop.value or state["table"]
        ok, msg = db.add_record(target, name_input.value, phone_input.value, address_input.value or "", facebook_input.value or "")
        if ok:
            state["selected_id"] = None
            name_input.value = phone_input.value = address_input.value = facebook_input.value = ""
            load_data(target)
            notify(msg, ft.Colors.GREEN_700)
        else:
            notify(msg, ft.Colors.RED_700)

    def update_record(e):
        if not state["selected_id"]:
            notify("اضغط على أيقونة القلم بجانب السجل في الجدول لتحديده أولاً ⚠️", ft.Colors.ORANGE_800)
            return
        ok, msg = db.update_record(state["table"], state["selected_id"], name_input.value or "", phone_input.value or "", address_input.value or "", facebook_input.value or "")
        clear_fields()
        notify(msg, ft.Colors.BLUE_700)

    def delete_record(e):
        if not state["selected_id"]:
            notify("حدد سجلاً من الجدول أولاً للحذف ⚠️", ft.Colors.ORANGE_800)
            return
        ok, msg = db.delete_record(state["table"], state["selected_id"])
        clear_fields()
        notify(msg, ft.Colors.RED_700)

    def refresh_and_sync(e):
        load_data(state["table"], search_input.value or "")
        notify("تم تحديث الجدول، وجاري المزامنة السحابية... 🔄", ft.Colors.TEAL_700)

        def worker():
            ok, msg = db.sync_records_with_cloud(state["table"])
            notify(msg, ft.Colors.GREEN_700 if ok else ft.Colors.ORANGE_800)

        threading.Thread(target=worker, daemon=True).start()

    search_input.on_change = lambda e: load_data(state["table"], e.control.value or "")

    # تحميل أولي صامت
    load_data("members", is_init=True)

    table_box = ft.Container(
        content=ft.Column(
            [ft.Row([data_table], scroll=ft.ScrollMode.ALWAYS)],
            scroll=ft.ScrollMode.ALWAYS,
            expand=True,
        ),
        expand=True,
        border=ft.Border.all(1, ft.Colors.GREY_800),
        border_radius=10,
        padding=6,
        bgcolor="#0F172A",
    )

    return ft.Container(
        padding=10,
        expand=True,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("إدارة السجلات والبيانات 👥", size=18, weight="bold", color=ft.Colors.AMBER),
                        ft.IconButton(
                            icon=ft.Icons.REFRESH,
                            icon_color=ft.Colors.AMBER,
                            tooltip="تحديث ومزامنة البيانات",
                            on_click=refresh_and_sync,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Row(
                    [
                        search_input,
                        ft.IconButton(
                            icon=ft.Icons.SEARCH,
                            icon_color=ft.Colors.AMBER,
                            tooltip="بحث",
                            on_click=lambda e: load_data(state["table"], search_input.value or ""),
                        ),
                    ],
                    spacing=5,
                ),
                ft.Row([name_input, phone_input], spacing=8),
                ft.Row([address_input, facebook_input], spacing=8),
                ft.Row(
                    [
                        role_drop,
                        ft.Button(content=ft.Text("إضافة", weight="bold"), on_click=add_record, bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE, expand=True),
                        ft.Button(content=ft.Text("تعديل", weight="bold"), on_click=update_record, bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE, expand=True),
                    ],
                    spacing=6,
                ),
                ft.Row(
                    [
                        ft.Button(content=ft.Text("حذف المحدد"), on_click=delete_record, bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE, expand=True),
                        ft.Button(content=ft.Text("تفريغ الحقول"), on_click=clear_fields, bgcolor=ft.Colors.GREY_700, color=ft.Colors.WHITE, expand=True),
                    ],
                    spacing=6,
                ),
                ft.Row(
                    [
                        ft.Button(content=ft.Text("عرض الأعضاء 👥"), on_click=lambda e: load_data("members"), bgcolor=ft.Colors.BLUE_GREY_800, color=ft.Colors.WHITE, expand=True),
                        ft.Button(content=ft.Text("عرض المخولين 🛡️"), on_click=lambda e: load_data("admins"), bgcolor=ft.Colors.AMBER_800, color=ft.Colors.WHITE, expand=True),
                    ],
                    spacing=6,
                ),
                status_label,
                table_box,
            ],
            spacing=8,
            expand=True,
        ),
    )
