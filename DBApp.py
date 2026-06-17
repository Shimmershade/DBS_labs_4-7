import psycopg2
from psycopg2 import sql
from datetime import datetime, timedelta
import sys
import os
from dotenv import load_dotenv
load_dotenv()


class DBApp:
    def __init__(self):
        try:
            self.conn = psycopg2.connect(
                host=os.getenv('DB_HOST', 'localhost'),
                port=os.getenv('DB_PORT', 5432),
                database=os.getenv('DB_NAME', 'demo'),
                user=os.getenv('DB_USER', 'postgres'),
                password=os.getenv('DB_PASSWORD')
            )

            self.cur = self.conn.cursor()
            self.cur.execute("SET search_path TO bookings, public;")
            self.cur.execute("SET client_encoding TO 'UTF8';")

            print("Подключение успешно.")
            print()

        except Exception as e:
            print("Ошибка подключения:", e)
            sys.exit(1)

    def close(self):
        try:
            self.cur.close()
            self.conn.close()
            print("Соединение с БД закрыто.")
        except:
            pass

    def show_menu(self):
        print()
        print("=" * 50)
        print("1. Показать динамику пассажиропотока")
        print("2. Заблокировать место на рейсе")
        print("3. Посадить пассажира (начисление миль)")
        print("4. Показать бонусные счета пассажиров")
        print("5. Показать заблокированные места")
        print("6. Показать последние посадки")
        print("0. Выход")
        print("-" * 50)

    def show_passenger_traffic(self):
        print()
        print("ДИНАМИКА ПАССАЖИРОПОТОКА")
        print("-" * 50)

        try:
            print("Введите даты в формате ГГГГ-ММ-ДД (например, 2026-01-01)")
            print("Или нажмите Enter для использования текущей даты")
            print()

            start_input = input("Дата начала (Enter - 30 дней назад): ").strip()
            end_input = input("Дата окончания (Enter - сегодня): ").strip()

            if start_input:
                start_date = datetime.strptime(start_input, '%Y-%m-%d').date()
            else:
                start_date = datetime.now().date() - timedelta(days=30)

            if end_input:
                end_date = datetime.strptime(end_input, '%Y-%m-%d').date()
            else:
                end_date = datetime.now().date()

            if start_date > end_date:
                print("Ошибка: дата начала не может быть позже даты окончания")
                return

            print()
            print(f"Период: {start_date} -> {end_date}")

            print("Выберите интервал группировки:")
            print("1. День")
            print("2. Неделя")
            print("3. Месяц")
            interval_choice = input("Ваш выбор (1-3, Enter - день): ").strip()

            if interval_choice == '2':
                interval_type = 'week'
            elif interval_choice == '3':
                interval_type = 'month'
            else:
                interval_type = 'day'

            self.cur.execute("""
                 SELECT * FROM bookings.get_passenger_traffic_dynamics(%s, %s, %s)
                 ORDER BY route, period_start
             """, (start_date, end_date, interval_type))

            results = self.cur.fetchall()

            if not results:
                print("Нет данных за указанный период")
                return

            print()
            print("РЕЗУЛЬТАТЫ:")
            print("-" * 60)

            current_route = None
            for row in results:
                if current_route != row[2]:
                    current_route = row[2]
                    print()
                    print(f"Маршрут: {current_route}")
                    print("-" * 40)

                print(f"  {row[0]} -> {row[1]} | Пассажиров: {row[3]} | Выручка: {row[4]} руб | Накоплено: {row[5]}")

            print()
            print(f"Всего записей: {len(results)}")
            print("-" * 60)

        except ValueError as e:
            print(f"Ошибка в формате даты: {e}")
            print("Используйте формат ГГГГ-ММ-ДД")
        except Exception as e:
            print(f"Ошибка: {e}")

    def block_seat(self):
        print()
        print("БЛОКИРОВКА МЕСТА")
        print("-" * 40)

        try:
            flight_id = int(input("Введите ID рейса: "))
            seat_no = input("Введите номер места (например, 12A): ").upper()
            reason = input("Причина блокировки: ")
            days = input("На сколько дней заблокировать (Enter - бессрочно): ")

            days_param = int(days) if days.strip() else None

            self.cur.execute("CALL bookings.block_seat(%s, %s, %s, %s)",
                             (flight_id, seat_no, reason, days_param))
            self.conn.commit()

            print(f"Место {seat_no} на рейс {flight_id} успешно заблокировано")

        except ValueError:
            print("Ошибка: ID рейса и дни должны быть числами")
        except Exception as e:
            print(f"Ошибка блокировки: {e}")
            self.conn.rollback()

    def board_passenger(self):
        print()
        print("ПОСАДКА ПАССАЖИРА")
        print("-" * 40)

        try:
            ticket_no = input("Номер билета: ")
            flight_id = int(input("ID рейса: "))
            seat_no = input("Номер места: ").upper()
            boarding_no = int(input("Номер посадки: "))

            boarding_time = datetime.now()

            self.cur.execute("""
                INSERT INTO bookings.boarding_passes 
                (ticket_no, flight_id, seat_no, boarding_no, boarding_time)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (ticket_no, flight_id) DO NOTHING
                RETURNING ticket_no, flight_id
            """, (ticket_no, flight_id, seat_no, boarding_no, boarding_time))

            result = self.cur.fetchone()
            self.conn.commit()

            if result:
                print()
                print(f"Пассажир успешно посажен!")
                print(f"  Билет: {result[0]}, Рейс: {result[1]}, Место: {seat_no}")
                print(f"  Триггер check_seat_availability: место проверено")
                print(f"  Триггер award_miles_on_boarding: мили начислены")

                self.cur.execute("""
                    SELECT miles_earned, price_paid, earning_type, earning_date
                    FROM bookings.miles_earnings
                    WHERE ticket_no = %s AND flight_id = %s
                    ORDER BY earning_date DESC
                    LIMIT 1
                """, (ticket_no, flight_id))

                miles = self.cur.fetchone()
                if miles:
                    print(f"  Начислено миль: {miles[0]} (за оплату {miles[1]} руб)")
            else:
                print("Пассажир уже был посажен на этот рейс")

        except psycopg2.Error as e:
            self.conn.rollback()
            if "заблокировано" in str(e):
                print(f"ОШИБКА: {e}")
                print("  Триггер check_seat_availability сработал и запретил посадку")
            else:
                print(f"Ошибка БД: {e}")
        except Exception as e:
            self.conn.rollback()
            print(f"Ошибка: {e}")

    def show_bonus_accounts(self):
        print()
        print("БОНУСНЫЕ СЧЕТА ПАССАЖИРОВ")
        print("-" * 40)

        try:
            self.cur.execute("""
                SELECT account_id, passenger_id, miles_balance, 
                       miles_earned_total, miles_burned_total,
                       created_at, updated_at
                FROM bookings.bonus_accounts
                ORDER BY miles_balance DESC
                LIMIT 10
            """)

            results = self.cur.fetchall()

            if not results:
                print("Нет зарегистрированных бонусных счетов")
                return

            for row in results:
                print(f"ID: {row[0]} | Пассажир: {row[1]}")
                print(f"  Баланс миль: {row[2]} | Всего заработано: {row[3]} | Потрачено: {row[4]}")
                print(f"  Создан: {row[5]} | Обновлен: {row[6]}")
                print("-" * 40)

        except Exception as e:
            print(f"Ошибка: {e}")

    def show_blocked_seats(self):
        print()
        print("ЗАБЛОКИРОВАННЫЕ МЕСТА")
        print("-" * 40)

        try:
            self.cur.execute("""
                SELECT bs.flight_id, bs.seat_no, bs.blocked_reason, 
                       bs.blocked_by, bs.blocked_from, bs.blocked_until,
                       bs.is_active
                FROM bookings.blocked_seats bs
                WHERE bs.is_active = TRUE
                  AND (bs.blocked_until IS NULL OR bs.blocked_until > CURRENT_TIMESTAMP)
                ORDER BY bs.blocked_from DESC
                LIMIT 10
            """)

            results = self.cur.fetchall()

            if not results:
                print("Нет активных блокировок мест")
                return

            for row in results:
                print(f"Рейс {row[0]}, Место {row[1]}")
                print(f"  Причина: {row[2]} | Кем: {row[3]}")
                print(f"  Заблокировано: {row[4]}")
                if row[5]:
                    print(f"  Активно до: {row[5]}")
                else:
                    print(f"  Бессрочная блокировка")
                print("-" * 40)

        except Exception as e:
            print(f"Ошибка: {e}")

    def show_recent_boardings(self):
        print()
        print("ПОСЛЕДНИЕ ПОСАДКИ")
        print("-" * 40)

        try:
            self.cur.execute("""
                SELECT bp.ticket_no, bp.flight_id, bp.seat_no, 
                       bp.boarding_no, bp.boarding_time,
                       me.miles_earned, me.price_paid
                FROM bookings.boarding_passes bp
                LEFT JOIN bookings.miles_earnings me ON bp.ticket_no = me.ticket_no 
                                           AND bp.flight_id = me.flight_id
                ORDER BY bp.boarding_time DESC
                LIMIT 10
            """)

            results = self.cur.fetchall()

            if not results:
                print("Нет записей о посадках")
                return

            for row in results:
                print(f"Билет: {row[0]} | Рейс: {row[1]} | Место: {row[2]}")
                print(f"  Время посадки: {row[4]}")
                if row[5]:
                    print(f"  Начислено миль: {row[5]} (оплачено: {row[6]} руб)")
                print("-" * 40)

        except Exception as e:
            print(f"Ошибка: {e}")

    def run(self):
        print()
        print("=" * 50)
        print("АВИАКОМПАНИЯ - СИСТЕМА УПРАВЛЕНИЯ")
        print("=" * 50)

        while True:
            self.show_menu()
            choice = input("Выберите действие (0-6): ").strip()

            if choice == '0':
                print("До свидания!")
                break
            elif choice == '1':
                self.show_passenger_traffic()
            elif choice == '2':
                self.block_seat()
            elif choice == '3':
                self.board_passenger()
            elif choice == '4':
                self.show_bonus_accounts()
            elif choice == '5':
                self.show_blocked_seats()
            elif choice == '6':
                self.show_recent_boardings()
            else:
                print("Неверный выбор. Пожалуйста, выберите 0-6")

            input("Нажмите Enter для продолжения...")


def main():
    app = DBApp()
    try:
        app.run()
    finally:
        app.close()


if __name__ == "__main__":
    main()