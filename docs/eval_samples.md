# ChatSQL 评测题目精选（动手试用版）

从两个公开基准里挑了 26 道代表题，按难度分组，每题附**中文大意、标准 SQL、agent 实测结果**，
方便你手动跑一遍感受效果（答对和答错的都选了，失败案例更能看出系统边界）。

## 怎么跑

**BIRD 题库**（默认配置）：

```bash
# 单问
uv run python cli.py --db <数据库名> "<英文问题>"

# 多轮对话模式
uv run python cli.py --db <数据库名> --chat

# 加 --verbose 可以看到完整的 ReAct 循环（每次工具调用和重试）
uv run python cli.py --db <数据库名> "<英文问题>" --verbose

# Web 界面（可选中数据库看 schema）
uv run streamlit run app.py
```

**Spider 题库**（用环境变量切换数据库根目录）：

```bash
CHATSQL_DB_ROOT=data/spider_data/dev_databases uv run python cli.py --db <数据库名> "<英文问题>"
```

> 注意：RAG 索引只建了 BIRD 的 11 个库，Spider 题目走的是纯 agent（无检索增强），
> 所以 Spider 题加不加 `--no-rag` 效果一样。

## 实测结果怎么看

- **实测**列是 2026-09 全量评测（deepseek-flash）的结果：✓ 答对 / ✗ 答错（附失败类型）
- 失败类型：`结果不对（语义错误）` = SQL 能执行但答非所问，自纠错修不了；`重试 3 轮后放弃` = agent 放弃了；`SQL 执行报错` = 生成的 SQL 跑不起来
- **生成有方差**：temperature=0 也做不到完全复现，你手动跑的结果可能和实测不同——这本身就是项目的一个发现（BIRD 回退题归因、Spider 45 题回退中 42 题首轮即分叉）

## BIRD mini_dev（500 题 / 11 库，agent + RAG 实测）

### Simple

#### 1. 用欧元支付的客户数和用捷克克朗支付的客户数之比是多少？
`debit_card_specializing` · qid 1471 · 实测 **✓**

**英文问题**：What is the ratio of customers who pay in EUR against customers who pay in CZK?

**运行**：`uv run python cli.py --db debit_card_specializing "What is the ratio of customers who pay in EUR against customers who pay in CZK?"`

**标准 SQL**：
```sql
SELECT CAST(SUM(IIF(Currency = 'EUR', 1, 0)) AS FLOAT) / SUM(IIF(Currency = 'CZK', 1, 0)) AS ratio FROM customers
```

#### 2. Angela Sanders 的专业是什么？
`student_club` · qid 1312 · 实测 **✓**

**英文问题**：What's Angela Sanders's major?

**运行**：`uv run python cli.py --db student_club "What's Angela Sanders's major?"`

**标准 SQL**：
```sql
SELECT T2.major_name FROM member AS T1 INNER JOIN major AS T2 ON T1.link_to_major = T2.major_id WHERE T1.first_name = 'Angela' AND T1.last_name = 'Sanders'
```

#### 3. 30609 号病人被诊断为什么病？列出该病人所有化验日期。
`thrombosis_prediction` · qid 1153 · 实测 **✓**

**英文问题**：What is the disease patient '30609' diagnosed with. List all the date of laboratory tests done for this patient.

**运行**：`uv run python cli.py --db thrombosis_prediction "What is the disease patient '30609' diagnosed with. List all the date of laboratory tests done for this patient."`

**标准 SQL**：
```sql
SELECT T1.Diagnosis, T2.Date FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T1.ID = 30609
```

#### 4. 2012 年最高的月消费额是多少？
`debit_card_specializing` · qid 1498 · 实测 **✗ 结果不对（语义错误）**

**英文问题**：What is the highest monthly consumption in the year 2012?

**运行**：`uv run python cli.py --db debit_card_specializing "What is the highest monthly consumption in the year 2012?"`

**标准 SQL**：
```sql
SELECT SUM(Consumption) FROM yearmonth WHERE SUBSTR(Date, 1, 4) = '2012' GROUP BY SUBSTR(Date, 5, 2) ORDER BY SUM(Consumption) DESC LIMIT 1
```

### Moderate

#### 5. 2012 年 LAM 客户群里消费最低的是谁？
`debit_card_specializing` · qid 1472 · 实测 **✓**

**英文问题**：In 2012, who had the least consumption in LAM?

**运行**：`uv run python cli.py --db debit_card_specializing "In 2012, who had the least consumption in LAM?"`

**标准 SQL**：
```sql
SELECT T1.CustomerID FROM customers AS T1 INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID WHERE T1.Segment = 'LAM' AND SUBSTR(T2.Date, 1, 4) = '2012' GROUP BY T1.CustomerID ORDER BY SUM(T2.Consumption) ASC LIMIT 1
```

#### 6. 参加了 "Women's Soccer" 活动的社团学生中，有多少人要 M 码 T 恤？
`student_club` · qid 1317 · 实测 **✓**

**英文问题**：Among the students from the Student_Club who attended the event "Women's Soccer", how many of them want a T-shirt that's in medium size?

**运行**：`uv run python cli.py --db student_club "Among the students from the Student_Club who attended the event \"Women's Soccer\", how many of them want a T-shirt that's in medium size?"`

**标准 SQL**：
```sql
SELECT COUNT(T1.event_id) FROM event AS T1 INNER JOIN attendance AS T2 ON T1.event_id = T2.link_to_event INNER JOIN member AS T3 ON T2.link_to_member = T3.member_id WHERE T1.event_name = 'Women''s Soccer' AND T3.t_shirt_size = 'Medium'
```

#### 7. 1997 年检查出的最严重血栓病例中，女性患者有多少？
`thrombosis_prediction` · qid 1164 · 实测 **✓**

**英文问题**：How many of the patients with the most serious thrombosis cases examined in 1997 are women?

**运行**：`uv run python cli.py --db thrombosis_prediction "How many of the patients with the most serious thrombosis cases examined in 1997 are women?"`

**标准 SQL**：
```sql
SELECT  COUNT(*) FROM Patient AS T1 INNER JOIN Examination AS T2 ON T1.ID = T2.ID WHERE T1.SEX = 'F' AND STRFTIME('%Y', T2.`Examination Date`) = '1997' AND T2.Thrombosis = 1
```

#### 8. 2013 年 SME 客户的月均消费是多少？
`debit_card_specializing` · qid 1473 · 实测 **✗ 结果不对（语义错误）**

**英文问题**：What was the average monthly consumption of customers in SME for the year 2013?

**运行**：`uv run python cli.py --db debit_card_specializing "What was the average monthly consumption of customers in SME for the year 2013?"`

**标准 SQL**：
```sql
SELECT AVG(T2.Consumption) / 12 FROM customers AS T1 INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID WHERE SUBSTR(T2.Date, 1, 4) = '2013' AND T1.Segment = 'SME'
```

#### 9. 社团成员参加人数超过 10 人的活动中，有多少是会议？
`student_club` · qid 1322 · 实测 **✗ 结果不对（语义错误）**

**英文问题**：Among the events attended by more than 10 members of the Student_Club, how many of them are meetings?

**运行**：`uv run python cli.py --db student_club "Among the events attended by more than 10 members of the Student_Club, how many of them are meetings?"`

**标准 SQL**：
```sql
SELECT T1.event_name FROM event AS T1  INNER JOIN attendance AS T2 ON T1.event_id = T2.link_to_event GROUP BY T1.event_id  HAVING COUNT(T2.link_to_event) > 10 EXCEPT SELECT T1.event_name  FROM event AS T1  WHERE T1.type = 'Meeting'
```

### Challenging

#### 10. 2012 年用捷克克朗支付和用欧元支付的客户，燃气消费差是多少？
`debit_card_specializing` · qid 1476 · 实测 **✓**

**英文问题**：What was the difference in gas consumption between CZK-paying customers and EUR-paying customers in 2012?

**运行**：`uv run python cli.py --db debit_card_specializing "What was the difference in gas consumption between CZK-paying customers and EUR-paying customers in 2012?"`

**标准 SQL**：
```sql
SELECT SUM(IIF(T1.Currency = 'CZK', T2.Consumption, 0)) - SUM(IIF(T1.Currency = 'EUR', T2.Consumption, 0)) FROM customers AS T1 INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID WHERE SUBSTR(T2.Date, 1, 4) = '2012'
```

#### 11. Elijah Allen 在九月和十月参加活动花费的平均总成本是多少？
`student_club` · qid 1339 · 实测 **✓**

**英文问题**：Calculate the total average cost that Elijah Allen spent in the events on September and October.

**运行**：`uv run python cli.py --db student_club "Calculate the total average cost that Elijah Allen spent in the events on September and October."`

**标准 SQL**：
```sql
SELECT AVG(T2.cost) FROM member AS T1 INNER JOIN expense AS T2 ON T1.member_id = T2.link_to_member WHERE T1.last_name = 'Allen' AND T1.first_name = 'Elijah' AND (SUBSTR(T2.expense_date, 6, 2) = '09' OR SUBSTR(T2.expense_date, 6, 2) = '10')
```

#### 12. SME/LAM/KAM 三个客户群中，2012 到 2013 年欧元支付消费涨幅最大和最小的各是谁？
`debit_card_specializing` · qid 1482 · 实测 **✗ 重试 3 轮后放弃**

**英文问题**：Which of the three segments—SME, LAM and KAM—has the biggest and lowest percentage increases in consumption paid in EUR between 2012 and 2013?

**运行**：`uv run python cli.py --db debit_card_specializing "Which of the three segments—SME, LAM and KAM—has the biggest and lowest percentage increases in consumption paid in EUR between 2012 and 2013?"`

**标准 SQL**：
```sql
SELECT CAST((SUM(IIF(T1.Segment = 'SME' AND T2.Date LIKE '2013%', T2.Consumption, 0)) - SUM(IIF(T1.Segment = 'SME' AND T2.Date LIKE '2012%', T2.Consumption, 0))) AS FLOAT) * 100 / SUM(IIF(T1.Segment = 'SME' AND T2.Date LIKE '2012%', T2.Consumption, 0)), CAST(SUM(IIF(T1.Segment = 'LAM' AND T2.Date LIKE '2013%', T2.Consumption, 0)) - SUM(IIF(T1.Segment = 'LAM' AND T2.Date LIKE '2012%', T2.Consumption, 0)) AS FLOAT) * 100 / SUM(IIF(T1.Segment = 'LAM' AND T2.Date LIKE '2012%', T2.Consumption, 0)) , CAST(SUM(IIF(T1.Segment = 'KAM' AND T2.Date LIKE '2013%', T2.Consumption, 0)) - SUM(IIF(T1.Segment = 'KAM' AND T2.Date LIKE '2012%', T2.Consumption, 0)) AS FLOAT) * 100 / SUM(IIF(T1.Segment = 'KAM' AND T2.Date LIKE '2012%', T2.Consumption, 0)) FROM customers AS T1 INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID
```

#### 13. "Yearly Kickoff" 会议的广告预算是 "October Meeting" 的几倍？
`student_club` · qid 1359 · 实测 **✗ 重试 3 轮后放弃**

**英文问题**：How many times was the budget in Advertisement for "Yearly Kickoff" meeting more than "October Meeting"?

**运行**：`uv run python cli.py --db student_club "How many times was the budget in Advertisement for \"Yearly Kickoff\" meeting more than \"October Meeting\"?"`

**标准 SQL**：
```sql
SELECT CAST(SUM(CASE WHEN T2.event_name = 'Yearly Kickoff' THEN T1.amount ELSE 0 END) AS REAL) / SUM(CASE WHEN T2.event_name = 'October Meeting' THEN T1.amount ELSE 0 END) FROM budget AS T1 INNER JOIN event AS T2 ON T1.link_to_event = T2.event_id WHERE T1.category = 'Advertisement' AND T2.type = 'Meeting'
```

#### 14. 1959/2/18 出生的病人，1981 年 11 月到 12 月总胆固醇下降率是多少？
`thrombosis_prediction` · qid 1185 · 实测 **✗ 结果不对（语义错误）**

**英文问题**：For the patient who was born on 1959/2/18, what is the decrease rate for his/her total cholesterol from November to December in 1981?

**运行**：`uv run python cli.py --db thrombosis_prediction "For the patient who was born on 1959/2/18, what is the decrease rate for his/her total cholesterol from November to December in 1981?"`

**标准 SQL**：
```sql
SELECT CAST((SUM(CASE WHEN T2.Date LIKE '1981-11-%' THEN T2.`T-CHO` ELSE 0 END) - SUM(CASE WHEN T2.Date LIKE '1981-12-%' THEN T2.`T-CHO` ELSE 0 END)) AS REAL) / SUM(CASE WHEN T2.Date LIKE '1981-12-%' THEN T2.`T-CHO` ELSE 0 END) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T1.Birthday = '1959-02-18'
```

## Spider dev（1034 题 / 20 库，纯 agent 实测）

### Easy

#### 15. 列出所有歌手的姓名、国籍、年龄，按年龄从大到小排序。
`concert_singer` · qid 2 · 实测 **✓**

**英文问题**：Show name, country, age for all singers ordered by age from the oldest to the youngest.

**运行**：`CHATSQL_DB_ROOT=data/spider_data/dev_databases uv run python cli.py --db concert_singer "Show name, country, age for all singers ordered by age from the oldest to the youngest."`

**标准 SQL**：
```sql
SELECT name ,  country ,  age FROM singer ORDER BY age DESC
```

#### 16. 宠物有多少种不同的类型？
`pets_1` · qid 55 · 实测 **✓**

**英文问题**：Find the number of distinct type of pets.

**运行**：`CHATSQL_DB_ROOT=data/spider_data/dev_databases uv run python cli.py --db pets_1 "Find the number of distinct type of pets."`

**标准 SQL**：
```sql
SELECT count(DISTINCT pettype) FROM pets
```

#### 17. 所有体育场的最大容量和平均容量是多少？
`concert_singer` · qid 16 · 实测 **✗ 结果不对（语义错误）**

**英文问题**：What is the maximum capacity and the average of all stadiums ?

**运行**：`CHATSQL_DB_ROOT=data/spider_data/dev_databases uv run python cli.py --db concert_singer "What is the maximum capacity and the average of all stadiums ?"`

**标准 SQL**：
```sql
select max(capacity), average from stadium
```

### Medium

#### 18. 来自法国的歌手，平均年龄、最小年龄、最大年龄各是多少？
`concert_singer` · qid 4 · 实测 **✓**

**英文问题**：What is the average, minimum, and maximum age of all singers from France?

**运行**：`CHATSQL_DB_ROOT=data/spider_data/dev_databases uv run python cli.py --db concert_singer "What is the average, minimum, and maximum age of all singers from France?"`

**标准 SQL**：
```sql
SELECT avg(age) ,  min(age) ,  max(age) FROM singer WHERE country  =  'France'
```

#### 19. 体重超过 10 的宠物有多少只？
`pets_1` · qid 45 · 实测 **✓**

**英文问题**：Find the number of pets whose weight is heavier than 10.

**运行**：`CHATSQL_DB_ROOT=data/spider_data/dev_databases uv run python cli.py --db pets_1 "Find the number of pets whose weight is heavier than 10."`

**标准 SQL**：
```sql
SELECT count(*) FROM pets WHERE weight  >  10
```

#### 20. 列出每个体育场的名字和该场馆举办的演唱会数量。
`concert_singer` · qid 22 · 实测 **✗ 结果不对（语义错误）**

**英文问题**：Show the stadium name and the number of concerts in each stadium.

**运行**：`CHATSQL_DB_ROOT=data/spider_data/dev_databases uv run python cli.py --db concert_singer "Show the stadium name and the number of concerts in each stadium."`

**标准 SQL**：
```sql
SELECT T2.name ,  count(*) FROM concert AS T1 JOIN stadium AS T2 ON T1.stadium_id  =  T2.stadium_id GROUP BY T1.stadium_id
```

### Hard

#### 21. 年龄大于平均值的歌手，他们的歌名都有哪些？
`concert_singer` · qid 13 · 实测 **✓**

**英文问题**：What are all the song names by singers who are older than average?

**运行**：`CHATSQL_DB_ROOT=data/spider_data/dev_databases uv run python cli.py --db concert_singer "What are all the song names by singers who are older than average?"`

**标准 SQL**：
```sql
SELECT song_name FROM singer WHERE age  >  (SELECT avg(age) FROM singer)
```

#### 22. 重量低于平均值的汽车是什么型号？
`car_1` · qid 98 · 实测 **✗ 结果不对（语义错误）**

**英文问题**：What is the model for the car with a weight smaller than the average?

**运行**：`CHATSQL_DB_ROOT=data/spider_data/dev_databases uv run python cli.py --db car_1 "What is the model for the car with a weight smaller than the average?"`

**标准 SQL**：
```sql
SELECT T1.model FROM CAR_NAMES AS T1 JOIN CARS_DATA AS T2 ON T1.MakeId  =  T2.Id WHERE T2.Weight  <  (SELECT avg(Weight) FROM CARS_DATA)
```

#### 23. 哪个城市的到达航班最多？
`flight_2` · qid 221 · 实测 **✗ 结果不对（语义错误）**

**英文问题**：Which city has most number of arriving flights?

**运行**：`CHATSQL_DB_ROOT=data/spider_data/dev_databases uv run python cli.py --db flight_2 "Which city has most number of arriving flights?"`

**标准 SQL**：
```sql
SELECT T1.City FROM AIRPORTS AS T1 JOIN FLIGHTS AS T2 ON T1.AirportCode  =  T2.DestAirport GROUP BY T1.City ORDER BY count(*) DESC LIMIT 1
```

### Extra

#### 24. 列出所有体育场的名字，除了 2014 年办过演唱会的。
`concert_singer` · qid 31 · 实测 **✓**

**英文问题**：Show names for all stadiums except for stadiums having a concert in year 2014.

**运行**：`CHATSQL_DB_ROOT=data/spider_data/dev_databases uv run python cli.py --db concert_singer "Show names for all stadiums except for stadiums having a concert in year 2014."`

**标准 SQL**：
```sql
SELECT name FROM stadium EXCEPT SELECT T2.name FROM concert AS T1 JOIN stadium AS T2 ON T1.stadium_id  =  T2.stadium_id WHERE T1.year  =  2014
```

#### 25. 养了狗但没养猫的学生，列出他们的名字。
`pets_1` · qid 66 · 实测 **✗ 结果不对（语义错误）**

**英文问题**：What is the first name of every student who has a dog but does not have a cat?

**运行**：`CHATSQL_DB_ROOT=data/spider_data/dev_databases uv run python cli.py --db pets_1 "What is the first name of every student who has a dog but does not have a cat?"`

**标准 SQL**：
```sql
SELECT T1.fname ,  T1.age FROM student AS T1 JOIN has_pet AS T2 ON T1.stuid  =  T2.stuid JOIN pets AS T3 ON T3.petid  =  T2.petid WHERE T3.pettype  =  'dog' AND T1.stuid NOT IN (SELECT T1.stuid FROM student AS T1 JOIN has_pet AS T2 ON T1.stuid  =  T2.stuid JOIN pets AS T3 ON T3.petid  =  T2.petid WHERE T3.pettype  =  'cat')
```

#### 26. 生产至少 2 个型号、且合作厂商超过 3 家的汽车制造商？列出 id 和厂商名。
`car_1` · qid 175 · 实测 **✗ SQL 执行报错**

**英文问题**：Which are the car makers which produce at least 2 models and more than 3 car makers ? List the id and the maker .

**运行**：`CHATSQL_DB_ROOT=data/spider_data/dev_databases uv run python cli.py --db car_1 "Which are the car makers which produce at least 2 models and more than 3 car makers ? List the id and the maker ."`

**标准 SQL**：
```sql
select t1.id ,  t1.maker from car_makers as t1 join model_list as t2 on t1.id  =  t2.maker group by t1.id having count(*)  >=  2 intersect select t1.id ,  t1.maker from car_makers as t1 join model_list as t2 on t1.id  =  t2.maker join car_names as t3 on t2.model  =  t3.model group by t1.id having count(*)  >  3;
```

## 建议的试用路径

1. 先跑 2~3 道 ✓ 的 simple/easy 题，感受正常流程
2. 跑 challenging 的 qid 1339（实测 ✓，attempts=3）加 `--verbose`，看自纠错闭环怎么把 SQL 修对
3. 跑 ✗ 的题（比如 qid 1498、spider qid 66），对比标准 SQL 和 agent 生成的 SQL，体会"语义错误修不了"的含义
4. 用 `--chat` 模式在自己选的数据库上自由提问，试试追问他表结构（agent 会主动调 schema 工具）
