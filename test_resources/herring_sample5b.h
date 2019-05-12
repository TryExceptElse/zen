#include <vector>
#include <string>

namespace sample {

/**
 * Sample class declaration
 */
class Foo {
 public:
  explicit Foo(/*test*/std::vector<int> numbers): numbers_(numbers) {}

  void Print() const;

  /** Method with changed definition */
  std::string get_shrubbery() const { return "Not another shrubbery"; }

 private:
  std::vector<int> numbers_;
};

}  // namespace sample
