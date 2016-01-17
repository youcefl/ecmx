# ecmx
A Python wrapper over GMP-ECM

ecmx is a simple, easily deployed wrapper over GMP-ECM which consists of a single Python file.

Getting started
===============

You will need Python (anything >= 3.3 should be OK), and of course GMP-ECM.
Once you have a Python environment and GMP-ECM in your PATH, create a text file
containing the number you want to factor e.g.

        > echo "(10^353-1)/(9*1781225293*1044667255801249)" > 10m353.n

Now, to run 128 curves at B1=26e7 using 16 threads with progress output every two
hours, you would enter

        > ecmx.py -t 16 -d 7200 -i 10m353.n -o 10m353_26e7.out -cs 128 26e7

After completion of the curves, the output file 10m353_26e7.out will contain
the output produced by the 16 instances of GMP-ECM and if a factor is found it
is reported to the console. Option -d is the number of seconds you want between
progress output.

Here is an example with a smaller number chosen to show the ouptut we get when
a factor is found and the cofactor is a probable prime which ends the factorization:

        > echo "(10^20+39)*(10^31+33)" > test.n
        > ecmx.py -t 2 -d 10 -i test.n -o test.out -cs 50 11e3 
        ecmx version 0.4.1
        Copyright Youcef Lemsafer (May 2014 - Jan 2016).
        | 2016-01-17 18:04:05,786 | 
        | 2016-01-17 18:04:05,787 | ecmx version 0.4.1
        | 2016-01-17 18:04:05,787 | 
        | 2016-01-17 18:04:06,789 | Running 25 curves at 11e3 (thread 1)...
        | 2016-01-17 18:04:06,789 | Running 25 curves at 11e3 (thread 2)...
        | 2016-01-17 18:04:08,793 | A factor has been found (thread 1), the cofactor is PRP!
        | 2016-01-17 18:04:08,797 | GMP-ECM output (thread 1):

        GMP-ECM 6.4.4 [configured with GMP 6.1.0, --enable-asm-redc] [ECM]
        Running on <hostname>
        Input number is (10^20+39)*(10^31+33) (52 digits)
        [Sun Jan 17 18:04:07 2016]
        Using MODMULN [mulredc:0, sqrredc:0]
        Using B1=11000, B2=11000-1873422, polynomial x^1, sigma=3881101407
        dF=256, k=3, d=2310, d2=13, i0=-8
        Expected number of curves to find a factor of n digits:
        35	40	45	50	55	60	65	70	75	80
        2924742	1.8e+08	1.5e+10	Inf	Inf	Inf	Inf	Inf	Inf	Inf
        Step 1 took 8ms
        Using 8 small primes for NTT
        Estimated memory usage: 586K
        Initializing tables of differences for F took 0ms
        Computing roots of F took 0ms
        Building F from its roots took 0ms
        Computing 1/F took 0ms
        Initializing table of differences for G took 4ms
        Computing roots of G took 0ms
        Building G from its roots took 0ms
        Computing roots of G took 0ms
        Building G from its roots took 0ms
        Computing G * H took 4ms
        Reducing  G * H mod F took 0ms
        Computing roots of G took 0ms
        Building G from its roots took 0ms
        Computing G * H took 4ms
        Reducing  G * H mod F took 0ms
        Computing polyeval(F,G) took 4ms
        Computing product of all F(g_i) took 0ms
        Step 2 took 16ms
        ********** Factor found in step 2: 100000000000000000039
        Found probable prime factor of 21 digits: 100000000000000000039
        Probable prime cofactor ((10^20+39)*(10^31+33))/100000000000000000039 has 32 digits

        | 2016-01-17 18:04:08,797 | Number is fully factored!!
        | 2016-01-17 18:04:08,798 | Ran 33 curves @ B1=11e3

Another example, to show how you can reduce the output of GMP-ECM, the following example
will also exhibit progress output and that ecmx keeps running curves when a factor is found
and the cofactor is composite.

        > echo "(10^22+9)*(10^35+69)*(10^36+67)" > test.n
        > ecmx.py -q -t 2 -d 30 -i test.n -o test.out -cs 50 5e4
        ecmx version 0.4.1
        Copyright Youcef Lemsafer (May 2014 - Jan 2016).
        | 2016-01-17 18:18:58,852 | 
        | 2016-01-17 18:18:58,852 | ecmx version 0.4.1
        | 2016-01-17 18:18:58,852 | 
        | 2016-01-17 18:18:59,854 | Running 100 curves at 5e4 (thread 1)...
        | 2016-01-17 18:18:59,854 | Running 100 curves at 5e4 (thread 2)...
        | 2016-01-17 18:19:03,860 | GMP-ECM output (thread 2):

        GMP-ECM 6.4.4 [configured with GMP 6.1.0, --enable-asm-redc] [ECM]
        Input number is (10^22+9)*(10^35+69)*(10^36+67) (94 digits)
        Using B1=50000, B2=50000-12746592, polynomial x^2, sigma=2790862391
        Step 1 took 76ms
        Step 2 took 68ms
        ********** Factor found in step 2: 10000000000000000000009
        Found probable prime factor of 23 digits: 10000000000000000000009
        Composite cofactor ((10^22+9)*(10^35+69)*(10^36+67))/10000000000000000000009 has 72 digits

        | 2016-01-17 18:19:04,857 | 55 curves completed @ B1=5e4 out of 200 (Elapsed time: 0:00:05.001352, avg curve duration: 0:00:00.090934s, ETA: 0:00:13.185383s).
        | 2016-01-17 18:19:05,861 | GMP-ECM output (thread 1):

        GMP-ECM 6.4.4 [configured with GMP 6.1.0, --enable-asm-redc] [ECM]
        Input number is (10^22+9)*(10^35+69)*(10^36+67) (94 digits)
        Using B1=50000, B2=50000-12746592, polynomial x^2, sigma=1877786664
        Step 1 took 56ms
        Step 2 took 48ms
        ********** Factor found in step 2: 10000000000000000000009
        Found probable prime factor of 23 digits: 10000000000000000000009
        Composite cofactor ((10^22+9)*(10^35+69)*(10^36+67))/10000000000000000000009 has 72 digits

        | 2016-01-17 18:19:10,863 | 160 curves completed @ B1=5e4 out of 200 (Elapsed time: 0:00:11.007507, avg curve duration: 0:00:00.068797s, ETA: 0:00:02.751877s).
        | 2016-01-17 18:19:11,868 | A factor has been found (thread 2)!
        | 2016-01-17 18:19:13,870 | A factor has been found (thread 1)!
        | 2016-01-17 18:19:13,870 | Ran 200 curves @ B1=5e4

That's it, happy factoring!



Command line reference
======================

To get some help, invoke ecmx with option -h (--help):

        > ecmx.py --help

        ecmx version 0.4.1
        Copyright Youcef Lemsafer (May 2014 - Jan 2016).
        usage: ecmx.py [-h] [-v] -t THREADS [-d DELTA_PROGRESS] [-q]
                       [-maxmem MAX_MEMORY] [-k STAGE2_STEPS] [-n] [-nn] -i INPUT_FILE
                       -o OUTPUT_PATH [-e ECM_PATH] -cs NUMBER_OF_CURVES B1

        optional arguments:
          -h, --help            show this help message and exit
          -v, --verbosity       Increase verbosity level.
          -t THREADS, --threads THREADS
                                Number of threads.
          -d DELTA_PROGRESS, --delta_progress DELTA_PROGRESS
                                The number of seconds between progress outputs.
          -q, --quiet           Make GMP-ECM less verbose.
          -maxmem MAX_MEMORY, --max_memory MAX_MEMORY
                                Maximum memory usage per thread.
          -k STAGE2_STEPS, --stage2_steps STAGE2_STEPS
                                Number of steps to perform in stage 2.
          -n, --nice            Run ecm in "nice" mode (below normal priority).
          -nn, --very_nice      Run ecm in "very nice" mode (idle priority).
          -i INPUT_FILE, --input_file INPUT_FILE
                                Input file.
          -o OUTPUT_PATH, --output_path OUTPUT_PATH
                                Output file path.
          -e ECM_PATH, --ecm_path ECM_PATH
                                Path of ecm executable.
          -cs NUMBER_OF_CURVES B1, --curves_spec NUMBER_OF_CURVES B1
                                Curves specification as <number of curves> <B1> (the
                                option can be specified multiple times e.g. -cs 960
                                1e6 -cs 2400 3e6).

The following options are passed as is to GMP-ECM: -maxmem MAX_MEMORY, -k STAGE2_STEPS,
-n (--nice), -nn (--very_nice), refer GMP-ECM documentation for more details about them.

Note that in case ecm is not in PATH or you want to use another executable than the one
in path option -e (--ecm_path) can be used to specify the path of the GMP-ECM executable.
