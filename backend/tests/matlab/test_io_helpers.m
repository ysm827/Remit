function test_io_helpers(helperDir)
addpath(helperDir);
original = pwd;
restore = onCleanup(@() cd(original));
folder = tempname;
mkdir(folder);
cd(folder);
fid = fopen('table.csv', 'w', 'n', 'UTF-8');
fprintf(fid, '编号,类别,数值\n001,甲,2\n002,,\n003,乙,bad\n');
fclose(fid);
[T, profile] = remit_read_table('table.csv', ["编号", "数值"]);
assert(T.('编号')(1) == "001");
assert(isstring(T.('类别')));
assert(profile.rows == 3 && numel(profile.columns) == 3);
values = remit_numeric_column(T(1:2,:), '数值');
assert(values(1) == 2 && isnan(values(2)));
try
    remit_numeric_column(T, '数值');
    error('Test:Expected', 'Missing conversion rejection');
catch exc
    assert(strcmp(exc.identifier, 'Remit:NumericColumn'));
end
c = struct('name', '基线', 'metric_name', 'cost', 'metric_value', 2.5, ...
    'runtime_seconds', 0.1, 'ran_ok', true, 'notes', '真实测试值');
payload.questions.ques1 = struct('sample_description', '测试', 'candidates', c);
remit_write_json('pilot_ques1_results.json', payload, 'questions');
old = fileread('pilot_ques1_results.json');
assert(contains(old, '"candidates":['));
result = jsondecode(old);
assert(result.questions.ques1.candidates.metric_value == 2.5);
payload.questions.ques1.candidates.metric_value = Inf;
payload.questions.ques1.candidates.runtime_seconds = -1;
try
    remit_write_json('pilot_ques1_results.json', payload, 'questions');
    error('Test:Expected', 'Missing schema rejection');
catch exc
    assert(strcmp(exc.identifier, 'Remit:Schema'));
    assert(contains(exc.message, 'metric_value') && contains(exc.message, 'runtime_seconds'));
end
assert(strcmp(old, fileread('pilot_ques1_results.json')));
fid = fopen('.remit-inputs.json', 'w'); fprintf(fid, '["attachment.json"]'); fclose(fid);
try
    remit_write_json('attachment.json', struct('x', 1));
    error('Test:Expected', 'Missing input protection');
catch exc
    assert(strcmp(exc.identifier, 'Remit:Path'));
end
assert(~isfile('attachment.json'));
disp('REMIT_IO_HELPERS_PASS');
end
