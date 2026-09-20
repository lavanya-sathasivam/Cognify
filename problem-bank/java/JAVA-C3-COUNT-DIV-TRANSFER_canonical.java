/** Reference solution for JAVA-C3-COUNT-DIV-TRANSFER (Count Cold Days).
 *
 * DATA ONLY: this file documents the canonical solution for humans and for
 * test-data review. It is NEVER executed by the Cognify pipeline — student
 * code runs only inside the existing execution-service Docker sandbox
 * (services/execution-service), and Step 12/13 tests use the existing
 * FakeSandboxRunner so no host interpreter ever runs untrusted code.
 */
public class Main {
    public static int countColdDays(int[] temps, int threshold) {
        int count = 0;
        for (int t : temps) {
            if (t < threshold) {
                count += 1;
            }
        }
        return count;
    }

    public static void main(String[] args) throws Exception {
        java.util.Scanner sc = new java.util.Scanner(System.in);
        if (!sc.hasNextInt()) {
            return;
        }
        int n = sc.nextInt();
        if (!sc.hasNextInt()) {
            return;
        }
        int threshold = sc.nextInt();
        int[] temps = new int[n];
        for (int i = 0; i < n && sc.hasNextInt(); i++) {
            temps[i] = sc.nextInt();
        }
        System.out.println(countColdDays(temps, threshold));
    }
}
